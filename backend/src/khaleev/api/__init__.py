"""Typed Pydantic models shared by the API, the services and the generation layer.

The models live in ``khaleev.api.schemas``; this package is only a namespace so
``khaleev.api.deps`` and ``khaleev.api.routes`` can sit beside them without ever
importing the application factory (which would create a cycle).
"""
