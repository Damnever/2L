# -*- coding: utf-8 -*-

from __future__ import print_function, division, absolute_import

import heapq
from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean
from sqlalchemy.sql import functions, expression
from sqlalchemy.exc import DataError, IntegrityError, ProgrammingError
from tzlocal import get_localzone

from app.base.roles import Roles
from app.models.base import Model
from app.models.user import User
from app.libs.db import db_session
from app.libs.sorts import hot


def _datetime_convert(date):
    return datetime(date.year, date.month, date.day, date.hour,
                    date.minute, date.second, date.microsecond,
                    get_localzone())


class Topic(Model):
    name = Column('name', String(30), unique=True, nullable=False)
    admin_id = Column('admin_id', Integer(), default=1)
    avatar = Column('avatar', Text(), nullable=False)
    description = Column('description', String(420), nullable=False)
    rules = Column('rules', Text(), nullable=False)
    why = Column('why', Text(), nullable=False)
    # 0 vote, 1 accept, -1 reject.
    state = Column('state', Integer(), default=0)
    date = Column('update_date', DateTime(timezone=True),
                  default=functions.now(), onupdate=functions.now())

    @classmethod
    def can_post(cls, topic_id):
        r = cls.query.with_entities(cls.state).filter(cls.id==topic_id)
        return r.first().state == 1

    @classmethod
    def page_list_all_accepted(cls, page, per_page):
        r = cls.query.filter(cls.state==1).order_by(expression.desc(cls.date))
        return r.paginate(page, per_page)

    @classmethod
    def page_list_all(cls, page, per_page):
        r = cls.query.order_by(expression.desc(cls.date))
        return r.paginate(page, per_page)

    @classmethod
    def page_list_by_user(cls, username, page, per_page):
        user = User.get_by_name(username)
        r = cls.query.filter(
            expression.and_(cls.admin_id==user.id, cls.state==1)
        ).order_by(expression.desc(cls.date))
        return r.paginate(page, per_page)

    @classmethod
    def get_by_name(cls, name):
        return cls.query.filter(cls.name==name).first()

    @classmethod
    def create(cls, name, created_name, avatar,
               description, rules, why, state=0):
        user = User.get_by_name(created_name)
        t = Topic(name=name, admin_id=user.id, avatar=avatar,
                  description=description, rules=rules,
                  why=why, state=state)
        try:
            db_session.add(t)
            db_session.commit()
            user.update_permission(Roles.TopicEdit.format(t.id))
        except (DataError, IntegrityError, ProgrammingError):
            cls.rollback()
            raise
        return t

    def update(self, description=None, rules=None, avatar=None, state=None):
        if description:
            self.description = description
        if rules:
            self.rules = rules
        if state:
            self.state = state
        try:
            db_session.add(self)
            db_session.commit()
        except (DataError, IntegrityError, ProgrammingError):
            db_session.roolback()
            raise

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'avatar': self.avatar,
            'administer': self.administer.username,
            'description': self.description,
            'rules': self.rules,
            'state': self.state,
            'why': self.why,
            'date': self.date,
        }

    @property
    def administer(self):
        return User.get(self.admin_id)


class Post(Model):
    topic_id = Column('topic_id', Integer(), index=True, nullable=False)
    author_id = Column('author_id', Integer(), index=True, nullable=False)
    title = Column('title', String(120), unique=True, index=True, nullable=False)
    created_date = Column('created_date', DateTime(timezone=True),
                          default=functions.now())
    update_date = Column('update_date', DateTime(timezone=True),
                         default=functions.now(), onupdate=functions.now())
    comment_date = Column('comment_date', DateTime(timezone=True),
                          default=functions.now())
    keywords = Column('keywords', String(120), nullable=False)
    content = Column('content', Text(), default='')
    keep_silent = Column('keep_silent', Boolean(), default=False)
    is_draft = Column('is_draft', Boolean(), default=False)

    @classmethod
    def get_by_title(cls, title):
        return cls.query.filter(cls.title==title).first()

    @classmethod
    def hot_list(cls, num=30):
        # Maybe -> ImportError: cycle import...
        from app.models.action import PostUpVote, PostDownVote

        hots, count = list(), 0
        # Use heapsort and query iterator to cut down memory usage...
        # http://stackoverflow.com/questions/1078383/sqlalchemy-difference-between-query-and-query-all-in-for-loops
        for post in cls.query:
            post_id, post_date = post.id, _datetime_convert(post.update_date)
            ups = PostUpVote.count_by_post(post_id)
            downs = PostDownVote.count_by_post(post_id)
            score = hot(ups, downs, post_date)
            if count < num:
                heapq.heappush(hots, (score, post))
                count += 1
            elif score > hots[0][0]:
                heapq.heappushpop(hots, (score, post))

        posts = list()
        while hots:
            item = heapq.heappop(hots)
            posts.append(item[1])
        return posts[::-1]

    @classmethod
    def page_list(cls, username, page, per_page):
        # ImportError: cycle import...
        from app.models.action import Subscription

        q = cls.query
        # If user logined, query subscribed topics.
        if username:
            subs = Subscription.list_by_user(username)
            topics = set([s.topic_id for s in subs])
            # If user subscribed topics.
            if topics:
                q = q.filter(cls.topic_id.in_(topics))
        q = q.order_by(expression.desc(cls.comment_date))
        return q.paginate(page, per_page)

    @classmethod
    def page_list_by_user(cls, username, page, per_page):
        user = User.get_by_name(username)
        q = cls.query.filter(cls.author_id==user.id).order_by(
            expression.desc(cls.comment_date))
        return q.paginate(page, per_page)

    @classmethod
    def page_list_by_topic(cls, topic_id, page, per_page):
        q = cls.query.filter(cls.topic_id==topic_id).order_by(
            expression.desc(cls.comment_date))
        return q.paginate(page, per_page)

    @classmethod
    def create(cls, author_name, topic_id, title, keywords,
               content='', keep_silent=False, is_draft=False):
        user = User.get_by_name(author_name)
        p = cls(
            topic_id=topic_id,
            author_id=user.id,
            title=title,
            keywords=keywords,
            content=content,
            keep_silent=keep_silent,
            is_draft=is_draft,
        )
        try:
            db_session.add(p)
            db_session.commit()
            user.update_permission(Roles.PostEdit.format(p.id))
        except (DataError, IntegrityError, ProgrammingError):
            db_session.rollback()
            raise
        return p

    def update(self, keywords=None, content=None,
               keep_silent=False, is_draft=None):
        if keywords:
            self.keywords = keywords
        self.content = content
        self.keep_silent = keep_silent
        if is_draft:
            self.is_draft = is_draft
        try:
            db_session.add(self)
            db_session.commit()
        except (DataError, IntegrityError, ProgrammingError):
            db_session.rollback()
            raise

    def to_dict(self):
        return {
            'id': self.id,
            'author_name': self.author.username,
            'author_avatar': self.author.profile.avatar,
            'topic_id': self.topic_id,
            'topic_name': self.topic.name,
            'title': self.title,
            'keywords': self.keywords,
            'content': self.content,
            'keep_silent': self.keep_silent,
            'created_date': self.created_date,
            'update_date': self.update_date,
        }

    def _new_comment(self, now):
        self.comment_date = now
        db_session.add(self)

    @property
    def author(self):
        return User.get(self.author_id)

    @property
    def topic(self):
        return Topic.get(self.topic_id)


class Comment(Model):
    post_id = Column('post_id', Integer(), index=True, nullable=False)
    author_id = Column('author_id', Integer(), index=True, nullable=False)
    date = Column('date', DateTime(timezone=True), default=functions.now())
    content = Column('content', Text(), nullable=False)

    @classmethod
    def latest_by_post(cls, post_id):
        cs = cls.query.filter(cls.post_id==post_id).order_by(
            expression.desc(cls.date)).limit(1)
        return cs.first()

    @classmethod
    def page_list(cls, page, per_page):
        p = cls.query.order_by(expression.asc(cls.date))
        return p.paginate(page, per_page)

    @classmethod
    def count_by_user(cls, username):
        user = User.get_by_name(username)
        return cls.query.filter(cls.author_id==user.id).count()

    @classmethod
    def count_by_post(cls, post_id):
        return cls.query.filter(cls.post_id==post_id).count()

    @classmethod
    def last_with_count(cls, post_id):
        q = cls.query.filter(cls.post_id==post_id)
        return q.count(), q.order_by('-id').first()

    @classmethod
    def page_list_by_user(cls, username, page, per_page):
        user = User.get_by_name(username)
        p = cls.query.order_by(
            expression.asc(cls.date)).filter(cls.author_id==user.id)
        return p.paginate(page, per_page)

    @classmethod
    def page_list_by_post(cls, post_id, page, per_page):
        p = cls.query.order_by(
            expression.asc(cls.date)).filter(cls.post_id==post_id)
        return p.paginate(page, per_page)

    @classmethod
    def create(cls, author_name, post_id, content):
        user = User.get_by_name(author_name)
        now = functions.now()
        Post.get(post_id)._new_comment(now)
        c = cls(author_id=user.id, post_id=post_id, content=content, date=now)
        try:
            db_session.add(c)
            db_session.commit()
        except (DataError, IntegrityError, ProgrammingError):
            db_session.rollback()
            raise
        return c

    def update(self, content):
        self.content = content
        try:
            db_session.add(self)
            db_session.commit()
        except (DataError, IntegrityError, ProgrammingError):
            db_session.rollback()
            raise

    def to_dict(self):
        return {
            'id': self.id,
            'author': self.author.username,
            'avatar': self.author.profile.avatar,
            'date': self.date,
            'content': self.content,
        }

    @property
    def author(self):
        if not hasattr(self, '_author'):
            self._author = User.get(self.author_id)
        return self._author

    @property
    def post(self):
        return Post.get(self.post_id)


class TopicComment(Model):
    topic_id = Column('topic_id', Integer(), index=True, nullable=False)
    author_id = Column('author_id', Integer(), index=True, nullable=False)
    date = Column('date', DateTime(timezone=True), default=functions.now())
    content = Column('content', Text(), nullable=False)

    @classmethod
    def latest_by_topic(cls, topic_id):
        cs = cls.query.filter(cls.topic_id==topic_id).order_by(
            expression.desc(cls.date)).limit(1)
        return cs.first()

    @classmethod
    def page_list(cls, page, per_page):
        p = cls.query.order_by(expression.asc(cls.date))
        return p.paginate(page, per_page)

    @classmethod
    def count_by_user(cls, username):
        user = User.get_by_name(username)
        return cls.query.filter(cls.author_id==user.id).count()

    @classmethod
    def count_by_topic(cls, topic_id):
        return cls.query.filter(cls.topic_id==topic_id).count()

    @classmethod
    def page_list_by_user(cls, username, page, per_page):
        user = User.get_by_name(username)
        p = cls.query.order_by(
            expression.asc(cls.date)).filter(cls.author_id==user.id)
        return p.paginate(page, per_page)

    @classmethod
    def page_list_by_topic(cls, topic_id, page, per_page):
        p = cls.query.order_by(
            expression.asc(cls.date)).filter(cls.topic_id==topic_id)
        return p.paginate(page, per_page)

    @classmethod
    def create(cls, author_name, topic_id, content):
        user = User.get_by_name(author_name)
        now = functions.now()
        Topic.get(topic_id)._new_comment(now)
        c = cls(author_id=user.id, topic_id=topic_id, content=content, date=now)
        try:
            db_session.add(c)
            db_session.commit()
        except (DataError, IntegrityError, ProgrammingError):
            db_session.rollback()
            raise
        return c

    def update(self, content):
        self.content = content
        try:
            db_session.add(self)
            db_session.commit()
        except (DataError, IntegrityError, ProgrammingError):
            db_session.rollback()
            raise

    def to_dict(self):
        return {
            'id': self.id,
            'author': self.author.username,
            'avatar': self.author.profile.avatar,
            'date': self.date,
            'content': self.content,
        }

    @property
    def author(self):
        if not hasattr(self, '_author'):
            self._author = User.get(self.author_id)
        return self._author

    def topic(self):
        return Topic.get(self.topic_id)
