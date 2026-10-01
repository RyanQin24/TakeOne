"""The one conversion between WGS-84 geodetic coordinates and TakeOne metres.

There is deliberately no second implementation of this anywhere in the tree.
Latitude and longitude stop here: everything downstream — obstacles, actor
marks, cart starts, IK, the compiler, the renderer — is scene-local metres,
exactly the space TakeOne already reasons in.

Local frame: +X along the anchor's compass heading, +Y 90 degrees
counter-clockwise from +X, +Z up. With ``heading_deg = 0`` that is plain ENU
rotated so +X is North; the site heading lets a scout point the local axis down
a courtyard instead of at the pole.
"""

from __future__ import annotations

import math

WGS84_A = 6378137.0
WGS84_F = 1.0 / 298.257223563
WGS84_B = WGS84_A * (1.0 - WGS84_F)
E2 = WGS84_F * (2.0 - WGS84_F)
EP2 = (WGS84_A * WGS84_A - WGS84_B * WGS84_B) / (WGS84_B * WGS84_B)


def _radius(lat_rad):
    s = math.sin(lat_rad)
    return WGS84_A / math.sqrt(1.0 - E2 * s * s)


def geodetic_to_ecef(lat_deg, lon_deg, alt_m=0.0):
    lat, lon = math.radians(lat_deg), math.radians(lon_deg)
    n = _radius(lat)
    cos_lat, sin_lat = math.cos(lat), math.sin(lat)
    return (
        (n + alt_m) * cos_lat * math.cos(lon),
        (n + alt_m) * cos_lat * math.sin(lon),
        (n * (1.0 - E2) + alt_m) * sin_lat,
    )


def ecef_to_geodetic(x, y, z):
    """Ferrari/Bowring closed form; sub-millimetre for terrestrial altitudes."""
    lon = math.atan2(y, x)
    p = math.hypot(x, y)
    if p < 1e-9:
        return (90.0 if z >= 0 else -90.0, math.degrees(lon), abs(z) - WGS84_B)
    theta = math.atan2(z * WGS84_A, p * WGS84_B)
    lat = math.atan2(
        z + EP2 * WGS84_B * math.sin(theta) ** 3,
        p - E2 * WGS84_A * math.cos(theta) ** 3,
    )
    n = _radius(lat)
    alt = p / math.cos(lat) - n
    return (math.degrees(lat), math.degrees(lon), alt)


def _enu_basis(lat_deg, lon_deg):
    lat, lon = math.radians(lat_deg), math.radians(lon_deg)
    sin_lat, cos_lat = math.sin(lat), math.cos(lat)
    sin_lon, cos_lon = math.sin(lon), math.cos(lon)
    east = (-sin_lon, cos_lon, 0.0)
    north = (-sin_lat * cos_lon, -sin_lat * sin_lon, cos_lat)
    up = (cos_lat * cos_lon, cos_lat * sin_lon, sin_lat)
    return east, north, up


def ecef_to_enu(anchor, x, y, z):
    ax, ay, az = geodetic_to_ecef(anchor.lat_deg, anchor.lon_deg, anchor.alt_m or 0.0)
    dx, dy, dz = x - ax, y - ay, z - az
    east, north, up = _enu_basis(anchor.lat_deg, anchor.lon_deg)
    return (
        east[0] * dx + east[1] * dy + east[2] * dz,
        north[0] * dx + north[1] * dy + north[2] * dz,
        up[0] * dx + up[1] * dy + up[2] * dz,
    )


def enu_to_ecef(anchor, e, n, u):
    ax, ay, az = geodetic_to_ecef(anchor.lat_deg, anchor.lon_deg, anchor.alt_m or 0.0)
    east, north, up = _enu_basis(anchor.lat_deg, anchor.lon_deg)
    return (
        ax + east[0] * e + north[0] * n + up[0] * u,
        ay + east[1] * e + north[1] * n + up[1] * u,
        az + east[2] * e + north[2] * n + up[2] * u,
    )


def enu_to_local(anchor, e, n, u=0.0):
    """Rotate ENU into the site frame. +X follows ``anchor.heading_deg``."""
    theta = math.radians(anchor.heading_deg)
    sin_t, cos_t = math.sin(theta), math.cos(theta)
    return (e * sin_t + n * cos_t, -e * cos_t + n * sin_t, u)


def local_to_enu(anchor, x, y, z=0.0):
    theta = math.radians(anchor.heading_deg)
    sin_t, cos_t = math.sin(theta), math.cos(theta)
    return (x * sin_t - y * cos_t, x * cos_t + y * sin_t, z)


def geodetic_to_local(anchor, lat_deg, lon_deg, alt_m=None):
    """Latitude/longitude to TakeOne scene-local metres. The boundary."""
    altitude = anchor.alt_m or 0.0 if alt_m is None else alt_m
    e, n, u = ecef_to_enu(anchor, *geodetic_to_ecef(lat_deg, lon_deg, altitude))
    return enu_to_local(anchor, e, n, u)


def local_to_geodetic(anchor, x_m, y_m, z_m=0.0):
    """TakeOne scene-local metres back to latitude/longitude, for display only."""
    e, n, u = local_to_enu(anchor, x_m, y_m, z_m)
    lat, lon, alt = ecef_to_geodetic(*enu_to_ecef(anchor, e, n, u))
    return (lat, lon, alt)


def great_circle_m(lat_a, lon_a, lat_b, lon_b):
    """Straight-line ground distance. This is never presented as a walking route."""
    phi_a, phi_b = math.radians(lat_a), math.radians(lat_b)
    d_phi = phi_b - phi_a
    d_lam = math.radians(lon_b - lon_a)
    h = math.sin(d_phi / 2) ** 2 + math.cos(phi_a) * math.cos(phi_b) * math.sin(d_lam / 2) ** 2
    return 2 * 6371008.8 * math.asin(min(1.0, math.sqrt(h)))


def bearing_deg(lat_a, lon_a, lat_b, lon_b):
    phi_a, phi_b = math.radians(lat_a), math.radians(lat_b)
    d_lam = math.radians(lon_b - lon_a)
    y = math.sin(d_lam) * math.cos(phi_b)
    x = math.cos(phi_a) * math.sin(phi_b) - math.sin(phi_a) * math.cos(phi_b) * math.cos(d_lam)
    return (math.degrees(math.atan2(y, x)) + 360.0) % 360.0
