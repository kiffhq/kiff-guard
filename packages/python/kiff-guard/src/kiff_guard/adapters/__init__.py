"""Framework adapters.

Each adapter is a thin shim translating one framework's pre-tool-execution
seam into a call to the framework-agnostic `Guard.evaluate`. The guard
logic lives in kiff_guard.guard; adapters add no governance logic of their
own.

Adapters import their host framework lazily (inside the factory), so
importing kiff_guard never requires any framework to be installed.
"""
