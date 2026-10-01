"""Test package marker.

LeRobot installs its own top-level `tests` package into site-packages. A regular
package wins over a namespace package regardless of sys.path order, so without
this file `from tests.support.devices import ...` resolves to LeRobot's tests and
fails to import.
"""
