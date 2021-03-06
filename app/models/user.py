# -*- coding: utf-8 -*-

from __future__ import print_function, division, absolute_import

from sqlalchemy.orm import relationship
from sqlalchemy.sql import functions, expression
from sqlalchemy.exc import DataError, IntegrityError, ProgrammingError
from sqlalchemy import (
    Column, Integer, String, Text, DateTime,
    ForeignKey, UniqueConstraint,
)

from app.models.base import Model
from app.models.permission import Permission
from app.settings import Level, Gold
from app.libs.db import db_session


class User(Model):
    username = Column('username', String(10), index=True,
                      unique=True, nullable=False)
    password = Column('password', String(40), nullable=False)
    email = Column('email', String(100), unique=True, default='')
    role = Column('role', Integer(), default=0)
    profile = relationship('Profile', uselist=False, backref='user')

    @classmethod
    def list_all(cls):
        return cls.query

    @classmethod
    def get_by_name(cls, username):
        return cls.query.filter(cls.username==username).first()

    @classmethod
    def get_by_email(cls, email):
        return cls.query.filter(cls.email==email).first()

    @classmethod
    def create(cls, **kwargs):
        user_attrs = dict()
        profile_attrs = dict()
        for k, v in kwargs.items():
            if hasattr(cls, k):
                user_attrs[k] = v
            elif hasattr(Profile, k):
                profile_attrs[k] = v
        profile = Profile(**profile_attrs)
        user_attrs.update({'profile': profile})
        user = cls(**user_attrs)
        try:
            db_session.add(user)
            db_session.add(profile)
            db_session.commit()
        except (DataError, IntegrityError, ProgrammingError):
            db_session.rollback()
            raise
        return user

    def delete(self):
        try:
            db_session.delete(self.profile)
            db_session.delete(self)
            db_session.commit()
        except (DataError, IntegrityError, ProgrammingError):
            db_session.rollback()
            raise

    def update(self, **kwargs):
        for k, v in kwargs.items():
            if hasattr(self, k):
                setattr(self, k, v)
            elif hasattr(self.profile, k):
                if k == 'gold':
                    v += getattr(self.profile, k)
                setattr(self.profile, k, v)

        if self.profile.gold >= Level['gold']['topic_creation']:
            self.role |= Permission.get_by_role('topic_creation').bit
        if self.profile.gold >= Level['gold']['vote']:
            self.role |= Permission.get_by_role('vote').bit
        try:
            db_session.add(self)
            db_session.commit()
        except (DataError, IntegrityError, ProgrammingError):
            db_session.rollback()
            raise

    def has_permission(self, role):
        per = Permission.get_by_role(role)
        if not per:
            return None
        r = self.query.filter((self.role&per.bit)>0)
        return r.first()

    def update_permission(self, role):
        p = Permission.create(role)
        self.role |= p.bit
        db_session.add(self)
        db_session.commit()

    def information(self):
        info = {
            'id': self.id,
            'username': self.username,
            'gold': self.profile.gold,
            'join_date': self.profile.join_date,
            'introduce': self.profile.introduce,
            'avatar': self.profile.avatar,
            'location': self.profile.location,
            'wiki': self.profile.wiki,
            'blog': self.profile.blog,
            'github': self.profile.github,
            'google': self.profile.google,
            'weibo': self.profile.weibo,
            'twitter': self.profile.twitter,
        }
        return info

    def following_count(self):
        return Following.get_count_by_userid(self.id)

    def blocked_count(self):
        return Blocked.get_count_by_userid(self.id)


class Profile(Model):
    user_id = Column('user_id', Integer(), ForeignKey('user.id'))
    gold = Column('gold', Integer(), nullable=False,
                  default=Gold['register'])
    join_date = Column('join_date', DateTime(timezone=True),
                       default=functions.now())
    introduce = Column('introduce', Text(300), default='You know, 2L~')
    avatar = Column('avatar', Text())
    location = Column('location', String(120), default='Earth')
    wiki = Column('wiki', Text(), default='')
    blog = Column('blog', String(100), default='')
    github = Column('github', String(100), default='')
    google = Column('google', String(100), default='')
    weibo = Column('weibo', String(100), default='')
    twitter = Column('twitter', String(100), default='')


class Following(Model):

    __table_args__ = (
        UniqueConstraint('user_id', 'following_id', name='f_usr_flw'),
    )

    user_id = Column('user_id', Integer(), index=True, nullable=False)
    following_id = Column('following_id', Integer(), index=True, nullable=False)

    @classmethod
    def followed(cls, user_id, following_id):
        r = cls.query.filter(expression.and_(
            cls.user_id==user_id, cls.following_id==following_id))
        return True if r.first() else False

    @classmethod
    def count_by_user(cls, username):
        user = User.get_by_name(username)
        return cls.query.filter(cls.user_id==user.id).count()

    @classmethod
    def list_following(cls, username):
        user = User.get_by_name(username)
        return cls.query.with_entities(
            cls.following_id).filter(cls.user_id==user.id).all()

    @classmethod
    def create(cls, username, following_name):
        user = User.get_by_name(username)
        following = User.get_by_name(following_name)
        f = cls(user_id=user.id, following_id=following.id)
        try:
            db_session.add(f)
            db_session.commit()
        except (DataError, IntegrityError, ProgrammingError):
            db_session.rollback()
            raise
        return f

    @classmethod
    def get_by_user_following(cls, username, following_name):
        user = User.get_by_name(username)
        following = User.get_by_name(following_name)
        r = cls.query.filter(expression.and_(cls.user_id==user.id,
                                             cls.following_id==following.id))
        return r.first()


class Blocked(Model):

    __table_args__ = (
        UniqueConstraint('user_id', 'blocked_id', name='b_usr_blk'),
    )

    user_id = Column('user_id', Integer(), index=True, nullable=False)
    blocked_id = Column('blocked_id', Integer(), index=True, nullable=False)

    @classmethod
    def blocked(cls, user_id, blocked_id):
        r = cls.query.filter(expression.and_(
            cls.user_id==user_id, cls.blocked_id==blocked_id))
        return True if r.first() else False

    @classmethod
    def count_by_user(cls, username):
        user = User.get_by_name(username)
        return cls.query.filter(cls.user_id==user.id).count()

    @classmethod
    def list_blocked(cls, username):
        user = User.get_by_name(username)
        return cls.query.with_entities(
            cls.blocked_id).filter(cls.user_id==user.id).all()

    @classmethod
    def create(cls, username, blocked_name):
        user = User.get_by_name(username)
        blocked = User.get_by_name(blocked_name)
        b = cls(user_id=user.id, blocked_id=blocked.id)
        try:
            db_session.add(b)
            db_session.commit()
        except (DataError, IntegrityError, ProgrammingError):
            db_session.rollback()
            raise
        return b

    @classmethod
    def get_by_user_blocked(cls, username, blocked_name):
        user = User.get_by_name(username)
        blocked = User.get_by_name(blocked_name)
        r = cls.query.filter(expression.and_(cls.user_id==user.id,
                                             cls.blocked_id==blocked.id))
        return r.first()
