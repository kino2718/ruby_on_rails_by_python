from google.cloud import datastore
from google.api_core.exceptions import Aborted
from datetime import datetime, timedelta, timezone
import copy
import re
from werkzeug.security import check_password_hash, generate_password_hash
from .errors import Errors
import secrets
import functools
from ..mailers import user_mailer
from flask_mail import Mail
from . import micropost as mpost
from . import relationship

class User:
    KIND_EMAILS = 'emails'
    KIND_USERS = 'users'
    EMAIL_PATTERN = re.compile(r'\A[\w+\-.]+@[a-z\d\-]+(\.[a-z\d\-]+)*\.[a-z]+\Z',
                               flags=re.IGNORECASE)

    def __init__(self, **kwargs):
        self.id = kwargs.get('id')
        self.name = kwargs.get('name')
        self.email = kwargs.get('email')
        self.created_at = kwargs.get('created_at')
        self.updated_at = kwargs.get('updated_at')
        self.password = kwargs.get('password')
        self.password_confirmation = kwargs.get('password_confirmation')
        self.password_digest = kwargs.get('password_digest')
        self.remember_token = kwargs.get('remember_token')
        self.remember_digest = kwargs.get('remember_digest')
        self.admin = kwargs.get('admin', False)
        self.activation_token = kwargs.get('activation_token')
        self.activation_digest = kwargs.get('activation_digest')
        self.activated = kwargs.get('activated', False)
        self.activated_at = kwargs.get('activated_at')
        self.reset_token = kwargs.get('reset_token')
        self.reset_digest = kwargs.get('reset_digest')
        self.reset_sent_at = kwargs.get('reset_sent_at')
        self.microposts = MyMicroposts(self)
        self.errors = Errors()

    def __repr__(self):
        return f'User(id={self.id.__repr__()}, ' +\
            f'name={self.name.__repr__()}, email={self.email.__repr__()}, ' +\
            f'created_at={self.created_at.__repr__()}, ' +\
            f'updated_at={self.updated_at.__repr__()}, ' +\
            f'password={self.password.__repr__()}, ' +\
            f'password_confirmation={self.password_confirmation.__repr__()}, ' +\
            f'password_digest={self.password_digest.__repr__()}, ' +\
            f'remember_token={self.remember_token.__repr__()}, ' +\
            f'remember_digest={self.remember_digest.__repr__()}, ' +\
            f'admin={self.admin.__repr__()}, ' +\
            f'activation_token={self.activation_token.__repr__()}, ' +\
            f'activation_digest={self.activation_digest.__repr__()}, ' +\
            f'activated={self.activated.__repr__()}, ' +\
            f'activated_at={self.activated_at.__repr__()}, ' +\
            f'reset_token={self.reset_token.__repr__()} ,' +\
            f'reset_digest={self.reset_digest.__repr__()}, ' +\
            f'reset_sent_at={self.reset_sent_at.__repr__()})'

    def __str__(self):
        return f'User(id={self.id}, name={self.name}, email={self.email}, ' +\
            f'created_at={self.created_at}, ' +\
            f'updated_at={self.updated_at}, ' +\
            f'password={self.password}, ' +\
            f'password_confirmation={self.password_confirmation}, ' +\
            f'password_digest={self.password_digest}, ' +\
            f'remember_token={self.remember_token}, ' +\
            f'remember_digest={self.remember_digest}, ' +\
            f'admin={self.admin}, ' +\
            f'activation_token={self.activation_token}, ' +\
            f'activation_digest={self.activation_digest}, ' +\
            f'activated={self.activated}, ' +\
            f'activated_at={self.activated_at}, ' +\
            f'reset_token={self.reset_token}, ' +\
            f'reset_digest={self.reset_digest}, ' +\
            f'reset_sent_at={self.reset_sent_at})'

    def __eq__(self, other):
        if not isinstance(other, User):
            return False
        # created_at, updated_at, activated_atはdatetime.datetime型と
        # google.api_core.datetime_helpers.DatetimeWithNanoseconds型を
        # 取るので比較には用いない。手抜き
        return \
            self.id==other.id and \
            self.name==other.name and \
            self.email==other.email and \
            self.password_digest==other.password_digest and \
            self.remember_digest==other.remember_digest and \
            self.admin==other.admin and \
            self.activation_token==other.activation_token and \
            self.activation_digest==other.activation_digest and \
            self.activated==other.activated and \
            self.reset_token==other.reset_token and \
            self.reset_digest==other.reset_digest and \
            self.reset_sent_at==other.reset_sent_at

    # decorator
    # methodではなく単にUser classのスコープ内の関数
    def create_activation_digest(f):
        @functools.wraps(f)
        def wrapper(self, *args, **kwargs):
            self.activation_token = User.new_token()
            self.activation_digest = User.digest(self.activation_token)
            return f(self, *args, **kwargs)
        return wrapper

    def valid(self):
        self.errors = Errors()
        v = True
        if (not self.name) or (not self.name.strip()):
            v = False
            self.errors.add('name', "name can't be blank")
        if self.name and (50 < len(self.name)):
            v = False
            self.errors.add('name', "name is too long")
        if (not self.email) or (not self.email.strip()):
            v = False
            self.errors.add('email', "email can't be blank")
        if self.email and (255 < len(self.email)):
            v = False
            self.errors.add('email', 'email is too long')
        if self.email and (not User.EMAIL_PATTERN.match(self.email)):
            v = False
            self.errors.add('email', 'email is invalid')
        if self._does_email_exist():
            v = False
            self.errors.add('email', 'email has already been taken')

        good_password = True
        if self.id:
            # 既存ユーザー。passwordブランクは許されるので
            # passwordに値が入っている場合のみチェック
            if self.password:
                if not self.password.strip():
                    # passwordが全て空白
                    good_password = False
                    v = False
                    self.errors.add('password', "password can't be blank")
                else:
                    if len(self.password) < 6:
                        # passwordの長さが6文字未満
                        good_password = False
                        v = False
                        self.errors.add('password', 'password is too short')
        else:
            # 新規ユーザー
            if not self.password or not self.password.strip():
                # passwordが空又はNone又は全て空白
                good_password = False
                v = False
                self.errors.add('password', "password can't be blank")
            else:
                if len(self.password) < 6:
                    # passwordの長さが文字未満
                    good_password = False
                    v = False
                    self.errors.add('password', 'password is too short')

        if good_password and self.password != self.password_confirmation:
            v = False
            self.errors.add('password_confirmation', "password confirmation doesn't match password")

        # if not v:
        #     print(f'Invalid: {self}. {self.errors}')
        return v

    def _check_email_unique_and_insert(self, client, key):
        # print(f'{self.name}: {self.email}登録開始')
        # emailアドレスが既に登録されているか確認
        entity = client.get(key)
        # print(f'{self.name}: メール登録済みかを確認')
        if entity is not None:
            # 既に登録済み
            # print(f'{self.name}: {self.email}は既に使用されている')
            return False

        # emailアドレスを登録
        entity = datastore.Entity(key=key)
        entity['created_at'] = datetime.now(timezone.utc)
        # print(f'{self.name}: メール登録開始')
        client.put(entity)
        return True

    def _insert_or_update_user(self, client, user):
        t = datetime.now(timezone.utc)
        user['name'] =  self.name
        user['email'] = self.email
        if not self.id:
            #新規登録
            user['created_at'] = t
        user['updated_at'] = t
        user['password_digest'] = self.password_digest
        user['remember_digest'] = self.remember_digest
        user['admin'] = self.admin
        user['activation_digest'] = self.activation_digest
        user['activated'] = self.activated
        user['activated_at'] = self.activated_at
        user['reset_digest'] = self.reset_digest
        user['reset_sent_at'] = self.reset_sent_at

        client.put(user)
        self.created_at = user['created_at']
        self.updated_at = user['updated_at']
        return user

    @create_activation_digest
    def _insert(self):
        client = datastore.Client()
        try:
            with client.transaction():
                email_key = client.key(User.KIND_EMAILS, self.email)
                user_key = client.key(User.KIND_USERS)
                user = datastore.Entity(user_key)
                if self._check_email_unique_and_insert(client, email_key):
                    user = self._insert_or_update_user(client, user)
                else:
                    return False
        except Aborted as e:
            # transaction競合のため失敗
            # print(f'{self.name}: 例外発生: {type(e)} {e}')
            # print(f'{self.name}: ユーザー登録失敗')
            return False

        # transactionの外で行うこと
        self.id = user.key.id

        # print(f'{self.name}: ユーザー登録終了')
        return True

    def _update(self):
        client = datastore.Client()
        user_key = client.key(User.KIND_USERS, self.id)
        user = client.get(user_key)
        if self.email != user['email']:
            # print('update: メールアドレスが違う')
            email_key = client.key(User.KIND_EMAILS, user['email'])
            try:
                with client.transaction():
                    # メールアドレスを削除
                    client.delete(email_key)
                    # 新しいメールアドレスをチェックしてユーザー情報をアップデート
                    email_key = client.key(User.KIND_EMAILS, self.email)
                    if self._check_email_unique_and_insert(client, email_key):
                        self._insert_or_update_user(client, user)
                    else:
                        return False
            except Aborted as e:
                # transaction競合のため失敗
                # print(f'{self.name}: 例外発生: {type(e)} {e}')
                # print(f'{self.name}: ユーザー更新失敗')
                return False
        else:
            # print('update: メールアドレスが同じ')
            self._insert_or_update_user(client, user)
        return True

    def save(self):
        # email を小文字に変換する
        if self.email is not None:
            self.email = self.email.lower()

        # user属性の有効性をチェックする
        if not self.valid():
            return False

        # password_digest を作成
        self.password_digest = User.digest(self.password)

        # idが存在する時はupdate、存在しない時はinsertを行う
        if self.id:
            return self._update()
        else:
            return self._insert()

    def update(self, **kwargs):
        # remember_token, remember_digestはここでは扱わずrememberメソッドで扱う
        # activation_token, activation_digestは_insertで作成する
        # activated, activated_atはupdate_attributeで扱う
        # reset_digest, reset_sent_atはupdate_attributeで扱う
        if len(kwargs) == 0:
            # print(f'test update: no update values')
            return True

        temp = copy.copy(self)
        dirty = False
        for k,v in kwargs.items():
            if k == 'name':
                if temp.name != v:
                    temp.name = v
                    dirty = True
            elif k == 'email':
                # email を小文字に変換する
                if temp.email.lower() != v.lower():
                    temp.email = v.lower()
                    dirty = True
            elif k == 'password':
                if temp.password != v:
                    temp.password = v
                    dirty = True
            elif k == 'password_confirmation':
                if temp.password_confirmation != v:
                    temp.password_confirmation = v
                    dirty = True
            elif k == 'admin':
                if temp.admin != v:
                    temp.admin = v
                    dirty = True
            else:
                raise AttributeError(f'{k} key is bad')

        # 変更する属性の有効性をチェックする
        if not temp.valid():
            self.errors = temp.errors
            return False

        if dirty:
            # password_digest を作成。passwordがFalseの時は以前のままにする
            if temp.password:
                temp.password_digest = User.digest(temp.password)
            if temp._update():
                self.name = temp.name
                self.email = temp.email
                self.updated_at = temp.updated_at
                self.password = temp.password
                self.password_confirmation = temp.password_confirmation
                self.password_digest = temp.password_digest
                self.admin = temp.admin
                return True
            else:
                return False
        return True

    def update_columns(self, **kwargs):
        if len(kwargs) == 0:
            return True

        temp = copy.copy(self)
        dirty = False
        for k,v in kwargs.items():
            if k == 'name':
                if temp.name != v:
                    temp.name = v
                    dirty = True
            elif k == 'email':
                # email を小文字に変換する
                if temp.email.lower() != v.lower():
                    temp.email = v.lower()
                    dirty = True
            elif k == 'password_digest':
                if temp.password_digest != v:
                    temp.password_digest = v
                    dirty = True
            elif k == 'remember_digest':
                if temp.remember_digest != v:
                    temp.remember_digest = v
                    dirty = True
            elif k == 'admin':
                if temp.admin != v:
                    temp.admin = v
                    dirty = True
            elif k == 'activation_digest':
                if temp.activation_digest != v:
                    temp.activation_digest = v
                    dirty = True
            elif k == 'activated':
                if temp.activated != v:
                    temp.activated = v
                    dirty = True
            elif k == 'activated_at':
                if temp.activated_at != v:
                    temp.activated_at = v
                    dirty = True
            elif k == 'reset_digest':
                if temp.reset_digest != v:
                    temp.reset_digest = v
                    dirty = True
            elif k == 'reset_sent_at':
                if temp.reset_sent_at != v:
                    temp.reset_sent_at = v
                    dirty = True
            else:
                raise AttributeError(f'{k} key is bad')

        if dirty:
            if temp._update():
                self.name = temp.name
                self.email = temp.email
                self.updated_at = temp.updated_at
                self.password_digest = temp.password_digest
                self.remember_digest = temp.remember_digest
                self.admin = temp.admin
                self.activation_digest = temp.activation_digest
                self.activated = temp.activated
                self.activated_at = temp.activated_at
                self.reset_digest = temp.reset_digest
                self.reset_sent_at = temp.reset_sent_at
                return True
            else:
                return False
        return True

    def update_attribute(self, k, v):
        return self.update_columns(**{k:v})

    @classmethod
    def create(cls, **kwargs):
        user = cls(**kwargs)
        res = user.save()
        if res:
            return user
        else:
            return None

    def reload(self):
        user = User.find(self.id)
        self.name = user.name
        self.email = user.email
        self.created_at = user.created_at
        self.updated_at = user.updated_at
        self.password = user.password
        self.password_confirmation = user.password_confirmation
        self.password_digest = user.password_digest
        self.remember_token = user.remember_token
        self.remember_digest = user.remember_digest
        self.admin = user.admin
        self.activation_token = user.activation_token
        self.activation_digest = user.activation_digest
        self.activated = user.activated
        self.activated_at = user.activated_at
        self.reset_token = user.reset_token
        self.reset_digest = user.reset_digest
        self.reset_sent_at = user.reset_sent_at
        self.errors = user.errors
        return self

    def destroy(self):
        client = datastore.Client()
        email_key = client.key(User.KIND_EMAILS, self.email)
        user_key = client.key(User.KIND_USERS, self.id)
        with client.transaction():
            client.delete(email_key)
            client.delete(user_key)
        # 1つのtransactionにたくさんの処理を入れられないようなので、transactionから外す
        for m in self.microposts():
            m.destroy()
        for r in relationship.Relationship.find_by(follower_id=self.id):
            r.destroy()
        for r in relationship.Relationship.find_by(followed_id=self.id):
            r.destroy()
        return self

    @staticmethod
    def find(id):
        if id is None:
            return None
        client = datastore.Client()
        key = client.key(User.KIND_USERS, id)
        entity = client.get(key)
        if entity is None:
            return None
        user = User(id=entity.key.id, **entity)
        return user

    @staticmethod
    def find_by(**kwargs):
        if not kwargs:
            return []
        client = datastore.Client()
        query = client.query(kind=User.KIND_USERS)
        for k,v in kwargs.items():
            if k == 'email':
                v = v.lower()
            query.add_filter(k, '=', v)
        entities = list(query.fetch())
        users = [User(id=entity.key.id, **entity) for entity in entities]
        return users

    @staticmethod
    def all():
        client = datastore.Client()
        query = client.query(kind=User.KIND_USERS)
        query.order = ['created_at']
        entities = list(query.fetch())
        users = [User(id=entity.key.id, **entity) for entity in entities]
        return users

    @staticmethod
    def paginate(page=None):
        if page is None:
            page = 1
        elif page < 1:
            raise IndexError('paginate: page must be greater than or equal to 1')
        limit = 30
        offset = (page-1)*limit
        client = datastore.Client()
        query = client.query(kind=User.KIND_USERS)
        query.order = ['created_at']
        entities = list(query.fetch(limit=limit, offset=offset))
        users = [User(id=entity.key.id, **entity) for entity in entities]
        return users

    @staticmethod
    def count():
        # 統計情報はリアルタイムで反映されないので使用できない
        # client = datastore.Client()
        # key = client.key('__Stat_Kind__', 'emails')
        # entity = client.get(key)
        # if entity is not None:
        #     count = entity.get('count')
        #     if count is not None:
        #         return count
        users = User.all()
        return len(users)

    def authenticate(self, p):
        if check_password_hash(self.password_digest, p):
            return self
        return None

    def authenticated(self, attribute, token):
        digest = None
        if attribute == 'remember':
            digest = self.remember_digest
        elif attribute == 'activation':
            digest = self.activation_digest
        elif attribute == 'reset':
            digest = self.reset_digest
        if not digest:
            return False
        return check_password_hash(digest, token)

    @staticmethod
    def digest(string):
        return generate_password_hash(string)

    @staticmethod
    def new_token():
        token = secrets.token_urlsafe()
        return token

    def remember(self):
        self.remember_token = User.new_token()
        digest = User.digest(self.remember_token)
        self.update_attribute('remember_digest', digest)

    def forget(self):
        self.update_attribute('remember_digest', None)

    # アカウントを有効にする
    def activate(self):
        self.update_attribute('activated', True)
        self.update_attribute('activated_at', datetime.now(timezone.utc))

    # 有効化用のメールを送信する
    def send_activation_email(self, app):
        msg = user_mailer.account_activation(self)
        mail = Mail(app)
        mail.send(msg)

    # パスワード再設定の属性を設定する
    def create_reset_digest(self):
        self.reset_token = User.new_token()
        self.update_attribute('reset_digest',  User.digest(self.reset_token))
        self.update_attribute('reset_sent_at', datetime.now(timezone.utc))

    # パスワード再設定のメールを送信する
    def send_password_reset_email(self, app):
        msg = user_mailer.password_reset(self)
        mail = Mail(app)
        mail.send(msg)

    def password_reset_expired(self):
        dt = datetime.now(timezone.utc) - self.reset_sent_at
        return 2*60*60 < dt.total_seconds()

    def feed(self):
        feed = []
        # 自分のmicroposts
        feed += self.microposts()
        # フォローしている人のmicroposts
        for u in self.following():
            feed += u.microposts()
        feed.sort(key=lambda x: x.created_at, reverse=True)
        return feed

    def _does_email_exist(self):
        client = datastore.Client()
        users = self.find_by(email=self.email)
        if len(users) == 0 or users[0].id == self.id:
            return False
        return True

    def active_relationships_create(self, followed_id):
        return relationship.Relationship.create(follower_id=self.id,
                                                followed_id=followed_id)

    def active_relationships_build(self, followed_id):
        return relationship.Relationship(follower_id=self.id,
                                         followed_id=followed_id)

    def active_relationships_find_by(self, followed_id):
        r = relationship.Relationship.find_by(follower_id=self.id,
                                              followed_id=followed_id)
        if r:
            return r[0]
        else:
            return None

    def following(self):
        rs = relationship.Relationship.find_by(follower_id=self.id)
        if rs:
            return [User.find(r.followed_id) for r in rs]
        else:
            return []

    def followers(self):
        rs = relationship.Relationship.find_by(followed_id=self.id)
        if rs:
            return [User.find(r.follower_id) for r in rs]
        else:
            return []

    def follow(self, other_user):
        self.active_relationships_create(other_user.id)

    def unfollow(self, other_user):
        rs = relationship.Relationship.find_by(follower_id=self.id,
                                              followed_id=other_user.id)
        if rs:
            for r in rs:
                r.destroy()

    def is_following(self, other_user):
        rs = relationship.Relationship.find_by(follower_id=self.id,
                                              followed_id=other_user.id)
        if rs:
            return True
        else:
            return False
# end of User class

class MyMicroposts():
    def __init__(self, user):
        self._user = user
        self._microposts = None
        self._count = None

    def __call__(self):
        self._get_microposts()
        return self._microposts

    def build(self, *args, **kwargs):
        m = mpost.Micropost(*args, user_id=self._user.id, **kwargs)
        return m

    def create(self, *args, **kwargs):
        m = mpost.Micropost.create(*args, user_id=self._user.id, **kwargs)
        if m and self._microposts:
            # キャッシュに追加
            self._microposts.insert(0, m)
            self._count += 1
        return m

    def find_by(self, **kwargs):
        kwargs.update({'user_id':self._user.id})
        ms = mpost.Micropost.find_by(**kwargs)
        return ms

    def count(self):
        self._get_microposts()
        return self._count

    def reset(self):
        self._microposts = None
        self._count = None

    def _get_microposts(self):
        if self._microposts is None:
            self._microposts = mpost.Micropost.find_by(user_id=self._user.id)
            self._count = len(self._microposts)
# end MyMicroposts class
