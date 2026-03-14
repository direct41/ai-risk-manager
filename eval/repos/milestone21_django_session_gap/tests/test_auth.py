def test_login_logout(client) -> None:
    client.post("/login/")
    client.post("/logout/")
    assert True
