from common import AUTHENTICITY_TOKEN_PATTERN, are_same_templates, log_in_as
from flask import get_flashed_messages, render_template
from sampleapp.models.user import User

SUCCESS = 200

def test_should_get_new(client):
    response = client.get('/signup')
    assert response.status_code==SUCCESS

def test_should_redirect_index_when_not_logged_in(client):
    with client:
        response = client.get('/users', follow_redirects=True)
        contents = response.data.decode(encoding='utf-8')

        # log in画面にredirectされていることを確認
        ref = render_template('sessions/new.html')
        assert are_same_templates(ref, contents)

def test_should_redirect_edit_when_not_logged_in(client, test_users):
    test_user = test_users['michael']
    with client:
        # 編集ページアクセス
        response = client.get(f'/users/{test_user.id}/edit',
                              follow_redirects=True)
        contents = response.data.decode(encoding='utf-8')
        m = AUTHENTICITY_TOKEN_PATTERN.search(contents)
        assert len(m.groups()) == 1
        token = m.groups()[0]

        # flashメッセージが存在することを確認
        flashed_message = get_flashed_messages()
        assert flashed_message

        # log in画面にredirectされていることを確認
        ref = render_template('sessions/new.html', csrf_token=token)
        assert are_same_templates(ref, contents)

def test_should_redirect_update_when_not_logged_in(client, test_users):
    test_user = test_users['michael']
    with client:
        # csrf tokenをsessionに設定する
        token = 'token'
        with client.session_transaction() as sess:
            sess['csrf_token'] = token

        response = client.post(
            f'/users/{test_user.id}',
            data={'_method': 'patch',
                  'name': test_user.name,
                  'email': test_user.email,
                  'password': '',
                  'password_confirmation': '',
                  'authenticity_token': token},
            follow_redirects=True)
        contents = response.data.decode(encoding='utf-8')

        # flashメッセージが存在することを確認
        flashed_message = get_flashed_messages()
        assert flashed_message

        # log in画面にredirectされていることを確認
        ref = render_template('sessions/new.html', csrf_token=token)
        assert are_same_templates(ref, contents)

def test_should_redirect_edit_when_logged_in_as_wrong_user(client, test_users):
    user = test_users['michael']
    other_user = test_users['archer']
    with client:
        # ログインする
        log_in_as(client, other_user.email)
        # 編集ページにアクセス
        response = client.get(f'/users/{user.id}/edit',
                              follow_redirects=True)
        contents = response.data.decode(encoding='utf-8')

        # flashメッセージが無いことを確認
        flashed_message = get_flashed_messages()
        assert not flashed_message

        # homeにredirectされていることを確認
        ref = render_template('static_pages/home.html',
                              micropost=other_user.microposts.build())
        contents = response.data.decode(encoding='utf-8')
        assert are_same_templates(ref, contents)

def test_should_redirect_update_when_logged_in_as_wrong_user(client, test_users):
    user = test_users['michael']
    other_user = test_users['archer']
    with client:
        # ログインする
        log_in_as(client, other_user.email)

        # csrf tokenをsessionに設定する
        token = 'token'
        with client.session_transaction() as sess:
            sess['csrf_token'] = token

        # patch method を投げる
        response = client.post(
            f'/users/{user.id}',
            data={'_method': 'patch',
                  'name': user.name,
                  'email': user.email,
                  'password': '',
                  'password_confirmation': '',
                  'authenticity_token': token},
            follow_redirects=True)
        contents = response.data.decode(encoding='utf-8')

        # flashメッセージが無いことを確認
        flashed_message = get_flashed_messages()
        assert not flashed_message

        # homeにredirectされていることを確認
        ref = render_template('static_pages/home.html',
                              micropost=other_user.microposts.build())
        assert are_same_templates(ref, contents)

def test_should_redirect_destroy_when_not_logged_in(client, test_users):
    user = test_users['michael']
    with client:
        # csrf tokenをsessionに設定する
        token = 'token'
        with client.session_transaction() as sess:
            sess['csrf_token'] = token

        # ユーザー数を保存する
        before_count = User.count()

        # delete method を投げる
        response = client.post(
            f'/users/{user.id}',
            data={'_method': 'delete',
                  'authenticity_token': token},
            follow_redirects=True)
        contents = response.data.decode(encoding='utf-8')

        # ユーザー数が変わらないことを確認する
        after_count = User.count()
        assert before_count == after_count

        # ログイン画面にリダイレクトされていることを確認
        ref = render_template('sessions/new.html', csrf_token=token)
        assert are_same_templates(ref, contents)

def test_should_redirect_destroy_when_logged_in_as_a_non_admin(client, test_users):
    user = test_users['michael']
    other_user = test_users['archer']
    with client:
        # ログインする
        log_in_as(client, other_user.email)

        # csrf tokenをsessionに設定する
        token = 'token'
        with client.session_transaction() as sess:
            sess['csrf_token'] = token

        # ユーザー数を保存する
        before_count = User.count()

        # delete method を投げる
        response = client.post(
            f'/users/{user.id}',
            data={'_method': 'delete',
                  'authenticity_token': token},
            follow_redirects=True)
        contents = response.data.decode(encoding='utf-8')

        # ユーザー数が変わらないことを確認する
        after_count = User.count()
        assert before_count == after_count

        # homeにredirectされていることを確認
        ref = render_template('static_pages/home.html',
                              micropost=other_user.microposts.build())
        assert are_same_templates(ref, contents)

def test_should_redirect_following_when_not_logged_in(client, test_users):
    user = test_users['michael']
    with client:
        response = client.get(f'/users/{user.id}/following', follow_redirects=True)
        contents = response.data.decode(encoding='utf-8')
        # log in画面にredirectされていることを確認
        ref = render_template('sessions/new.html')
        assert are_same_templates(ref, contents)

def test_should_redirect_followers_when_not_logged_in(client, test_users):
    user = test_users['michael']
    with client:
        response = client.get(f'/users/{user.id}/followers', follow_redirects=True)
        contents = response.data.decode(encoding='utf-8')
        # log in画面にredirectされていることを確認
        ref = render_template('sessions/new.html')
        assert are_same_templates(ref, contents)
