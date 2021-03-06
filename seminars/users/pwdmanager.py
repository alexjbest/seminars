#!/usr/bin/env python
# -*- encoding: utf-8 -*-
from __future__ import print_function
from __future__ import absolute_import
from six import string_types, text_type
import bcrypt
# store passwords, check users, ...
# password hashing is done with fixed and variable salting
# Author: Harald Schilly <harald.schilly@univie.ac.at>
# Modified : Chris Brady and Heather Ratcliffe

from seminars import db
from lmfdb.backend.base import PostgresBase
from lmfdb.backend.encoding import Array
from psycopg2.sql import SQL, Identifier, Placeholder
from datetime import datetime, timedelta
from pytz import UTC

from .main import logger, FLASK_LOGIN_VERSION, FLASK_LOGIN_LIMIT
from distutils.version import StrictVersion

# Read about flask-login if you are unfamiliar with this UserMixin/Login
from flask_login import UserMixin, AnonymousUserMixin

class PostgresUserTable(PostgresBase):
    def __init__(self):
        PostgresBase.__init__(self, 'db_users', db)
        # never narrow down the rmin-rmax range, only increase it!
        self.rmin, self.rmax = -10000, 10000
        self._rw_userdb = db.can_read_write_userdb()
        cur = self._execute(SQL("SELECT column_name FROM information_schema.columns WHERE table_schema = %s AND table_name = %s"), ['userdb', 'users'])
        self._cols = [rec[0] for rec in cur]
        self._name = "userdb.users"


    def can_read_write_userdb(self):
        return self._rw_userdb


    def bchash(self, pwd):
        """
        Generate a bcrypt based password hash.
        """
        return bcrypt.hashpw(pwd.encode('utf-8'), bcrypt.gensalt())

    def generate_key(self):
        return ''.join([random.choice(string.ascii_letters + string.digits) for n in range(32)])

    def new_user(self, **kwargs):
        """
        Creates a new user.
        Required keyword arguments:
            - email
            - password
            - full_name
            - approver
        """
        for col in ["email", "password", "full_name", "approver"]:
            assert col in kwdargs
        kwargs['password'] = bchash(kwargs['password'])
        for col in ['email_confirmed', 'admin', 'editor', 'creator']:
            kwargs[key] = kwdargs.get(key, False)
        kwargs['email_reset_time'] = kwdargs.get(UTC.localize(datetime(1970,1,1,)))
        kwargs['email_reset_code'] = kwdargs.get("email_reset_code", None)
        kwargs['homepage'] = kwargs.get('homepage', None)
        kwargs['timezone'] = kwargs.get('timezone', "America/New York")
        kwargs['location'] = None
        kwargs['created'] = datetime.now(UTC)
        kwargs['ics_key'] = self.generate_key()


    def change_password(self, email, newpwd):
        if self._rw_userdb:
            updater = SQL("UPDATE {} SET {} = %s WHERE {} = %s").format(
                map(IdentifierWrapper, [self._name, "password", "email"]))
            self._execute(updater, [self.bchash(newpwd), email])
            logger.info("password for %s changed!" % email)
            return True
        else:
            logger.info("no attempt to change password, not enough privileges")
            return False




######## OLD #########
######## OLD #########
######## OLD #########
######## OLD #########
    def new_user(self, uid, pwd=None, full_name=None, about=None, url=None):
        """
        generates a new user, asks for the password interactively,
        and stores it in the DB. This is now replaced with bcrypt version
        """
        if not self._rw_userdb:
            logger.info("no attempt to create user, not enough privileges")
            return SeminarsAnonymousUser()

        if self.user_exists(uid):
            raise Exception("ERROR: User %s already exists" % uid)
        if not pwd:
            from getpass import getpass
            pwd_input = getpass("Enter  Password: ")
            pwd_input2 = getpass("Repeat Password: ")
            if pwd_input != pwd_input2:
                raise Exception("ERROR: Passwords do not match!")
            pwd = pwd_input
        password = self.bchash(pwd)
        from datetime import datetime
        #TODO: use identifiers
        insertor = SQL(u"INSERT INTO userdb.users (username, password, created, full_name, about, url) VALUES (%s, %s, %s, %s, %s, %s)")
        self._execute(insertor, [uid, password, datetime.utcnow(), full_name, about, url])
        new_user = SeminarsUser(uid)
        return new_user



    def user_exists(self, uid):
        selecter = SQL("SELECT username FROM userdb.users WHERE username = %s")
        cur = self._execute(selecter, [uid])
        return cur.rowcount > 0

    def get_user_list(self):
        """
        returns a list of tuples: [('username', 'full_name'),…]
        If full_name is None it will be replaced with username.
        """
        #TODO: use identifiers
        selecter = SQL("SELECT username, full_name FROM userdb.users")
        cur = self._execute(selecter)
        return [(uid, full_name or uid) for uid, full_name in cur]

    def authenticate(self, uid, pwd, bcpass=None, oldpass=None):
        if not self._rw_userdb:
            logger.info("no attempt to authenticate, not enough privileges")
            return False

        #TODO: use identifiers
        selecter = SQL("SELECT password FROM userdb.users WHERE username = %s")
        cur = self._execute(selecter, [uid])
        if cur.rowcount == 0:
            raise ValueError("User not present in database!")
        bcpass = cur.fetchone()[0]
        return bcpass == self.bchash(pwd, existing_hash = bcpass)

    def save(self, data):
        if not self._rw_userdb:
            logger.info("no attempt to save, not enough privileges")
            return;

        data = dict(data) # copy
        uid = data.pop("username", None)
        if not uid:
            raise ValueError("data must contain username")
        if not self.user_exists(uid):
            raise ValueError("user does not exist")
        if not data:
            raise ValueError("no data to save")
        fields, values = zip(*data.items())
        updater = SQL("UPDATE userdb.users SET ({0}) = ({1}) WHERE username = %s").format(SQL(", ").join(map(Identifier, fields)), SQL(", ").join(Placeholder() * len(values)))
        self._execute(updater, list(values) + [uid])

    def lookup(self, uid):
        selecter = SQL("SELECT {0} FROM userdb.users WHERE username = %s").format(SQL(", ").join(map(Identifier, self._cols)))
        cur = self._execute(selecter, [uid])
        if cur.rowcount == 0:
            raise ValueError("user does not exist")
        if cur.rowcount > 1:
            raise ValueError("multiple users with same username!")
        return {field:value for field,value in zip(self._cols, cur.fetchone()) if value is not None}

    def full_names(self, uids):
        #TODO: use identifiers
        selecter = SQL("SELECT username, full_name FROM userdb.users WHERE username = ANY(%s)")
        cur = self._execute(selecter, [Array(uids)])
        return [{k:v for k,v in zip(["username","full_name"], rec)} for rec in cur]

    def create_tokens(self, tokens):
        if not self._rw_userdb:
            return;

        insertor = SQL("INSERT INTO userdb.tokens (id, expire) VALUES %s")
        now = datetime.utcnow()
        tdelta = timedelta(days=1)
        exp = now + tdelta
        self._execute(insertor, [(t, exp) for t in tokens], values_list=True)

    def token_exists(self, token):
        if not self._rw_userdb:
            logger.info("no attempt to check if token exists, not enough privileges")
            return False;
        selecter = SQL("SELECT 1 FROM userdb.tokens WHERE id = %s")
        cur = self._execute(selecter, [token])
        return cur.rowcount == 1

    def delete_old_tokens(self):
        if not self._rw_userdb:
            logger.info("no attempt to delete old tokens, not enough privileges")
            return;
        deletor = SQL("DELETE FROM userdb.tokens WHERE expire < %s")
        now = datetime.utcnow()
        tdelta = timedelta(days=8)
        cutoff = now - tdelta
        self._execute(deletor, [cutoff])

    def delete_token(self, token):
        if not self._rw_userdb:
            return;
        deletor = SQL("DELETE FROM userdb.tokens WHERE id = %s")
        self._execute(deletor, [token])

    def change_colors(self, uid, new_color):
        updator = SQL("UPDATE userdb.users SET color_scheme = %s WHERE username = %s")
        self._execute(updator, [new_color, uid])

userdb = PostgresUserTable()

class SeminarsUser(UserMixin):
    """
    The User Object
    """
    properties = userdb._cols

    def __init__(self, uid):
        if not isinstance(uid, string_types):
            raise Exception("Username is not a string")

        self._uid = uid
        self._authenticated = False
        self._dirty = False  # flag if we have to save
        self._data = dict([(_, None) for _ in SeminarsUser.properties])

        if userdb.user_exists(uid):
            self._data.update(userdb.lookup(uid))

    @property
    def name(self):
        return self.full_name or self._data.get('username')

    @property
    def full_name(self):
        return self._data['full_name']

    @full_name.setter
    def full_name(self, full_name):
        self._data['full_name'] = full_name
        self._dirty = True

    @property
    def email(self):
        return self._data['email']

    @email.setter
    def email(self, email):
        self._data['email'] = email
        self._dirty = True

    @property
    def email_confirmed(self):
        return self._data['email_confirmed']

    @email_confirmed.setter
    def email_confirmed(self, confirmed):
        self._data['email_confirmed'] = confirmed
        self._dirty = True

    @property
    def email_reset_code(self):
        return self._data['email_reset_code']

    @email_reset_code.setter
    def email_reset_code(self, code):
        self._data['email_reset_code'] = code
        self._dirty = True

    @property
    def email_reset_time(self):
        return self._data['email_reset_time']

    @email_reset_time.setter
    def email(self, time):
        self._data['email_reset_time'] = time
        self._dirty = True

    @property
    def homepage(self):
        return self._data['homepage']

    @homepage.setter
    def homepage(self, url):
        if not url.startswith("http://") and not url.startswith("https://"):
            url = "http://" + url
        self._data['homepage'] = url
        self._dirty = True

    @property
    def created(self):
        return self._data.get('created')

    @property
    def id(self):
        return self._data['username']

    def is_anonymous(self):
        """required by flask-login user class"""
        if StrictVersion(FLASK_LOGIN_VERSION) < StrictVersion(FLASK_LOGIN_LIMIT):
            return not self.is_authenticated()
        return not self.is_authenticated

    def is_admin(self):
        return self._data.get("admin", False)

    def make_admin(self):
        self._data["admin"] = True
        self._dirty = True

    def is_editor(self):
        return self._data.get("editor", False)

    def make_editor(self):
        self._data["editor"] = True
        self._dirty = True

    def is_creator(self):
        return self._data.get("creator", False)

    def make_creator(self):
        self._data["creator"] = True
        self._dirty = True

    def authenticate(self, pwd):
        """
        checks if the given password for the user is valid.
        @return: True: OK, False: wrong password.
        """
        if 'password' not in self._data:
            logger.warning("no password data in db for '%s'!" % self._uid)
            return False
        self._authenticated = userdb.authenticate(self._uid, pwd)
        return self._authenticated

    def save(self):
        if not self._dirty:
            return
        logger.debug("saving '%s': %s" % (self.id, self._data))
        userdb.save(self._data)
        self._dirty = False

class SeminarsAnonymousUser(AnonymousUserMixin):
    """
    The sole purpose of this Anonymous User is the 'is_admin' method
    and probably others.
    """
    def is_admin(self):
        return False

    def is_editor(self):
        return False

    def is_creator(self):
        return False

    def name(self):
        return "Anonymous"

    # For versions of flask_login earlier than 0.3.0,
    # AnonymousUserMixin.is_anonymous() is callable. For later versions, it's a
    # property. To match the behavior of SeminarsUser, we make it callable always.
    def is_anonymous(self):
        return True

if __name__ == "__main__":
    print("Usage:")
    print("add user")
    print("remove user")
    print("…")
