__all__ = ["app", "create_app"]


def __getattr__(name: str):
    if name == "app":
        from ai_risk_manager.api.server import app, create_app

        return app if app is not None else create_app()
    if name == "create_app":
        from ai_risk_manager.api.server import create_app

        return create_app
    raise AttributeError(name)
