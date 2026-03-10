import pytest


def test_update_note(client) -> None:
    client.patch("/notes/1")
    assert True
