# Copyright (c) 2025 Agentspan
# Licensed under the MIT License. See LICENSE file in the project root for details.

"""Compat shim: register ``runtime_metadata`` on conductor-python's ``Task`` model.

The server delivers resolved worker secrets on the wire-only ``Task.runtimeMetadata``
field (resolved by the conductor core at poll from the names declared on
``TaskDef.runtimeMetadata``). Published ``conductor-python`` releases do not carry the
field yet, and the swagger-style deserializer drops any JSON key that is not registered
in ``Task.swagger_types``/``attribute_map`` — so without this shim the delivered values
never reach the ``Task`` object.

This registers the field on the client model at import time (idempotent), exactly as the
upstream model change would:

* ``swagger_types['runtime_metadata'] = 'dict(str, str)'``
* ``attribute_map['runtime_metadata'] = 'runtimeMetadata'``
* a ``runtime_metadata`` property + constructor kwarg (the deserializer builds models via
  ``klass(**kwargs)``)

Delete this module and the call sites once conductor-python ships ``Task.runtime_metadata``.
"""

from __future__ import annotations


def ensure_runtime_metadata_field() -> None:
    """Idempotently register ``runtime_metadata`` on ``conductor.client``'s ``Task`` model."""
    from conductor.client.http.models.task import Task

    if "runtime_metadata" in getattr(Task, "swagger_types", {}):
        return  # upstream model (or a prior call) already carries the field

    original_init = Task.__init__

    def _init(self, *args, **kwargs):  # noqa: ANN001, ANN202 - mirrors upstream signature
        runtime_metadata = kwargs.pop("runtime_metadata", None)
        original_init(self, *args, **kwargs)
        self._runtime_metadata = runtime_metadata

    Task.__init__ = _init
    Task.swagger_types["runtime_metadata"] = "dict(str, str)"
    Task.attribute_map["runtime_metadata"] = "runtimeMetadata"
    Task.runtime_metadata = property(
        lambda self: getattr(self, "_runtime_metadata", None),
        lambda self, value: setattr(self, "_runtime_metadata", value),
    )
