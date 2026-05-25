"""
Map widget: Leaflet map embedded in a QWebEngineView.
Uses QWebChannel for bidirectional Python <-> JS communication.
Served from a local HTTP server so tiles load correctly (file:// blocks tiles).
"""

import json
from PySide6.QtCore import QObject, Signal, Slot, QUrl
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtWebChannel import QWebChannel

from ..core.webserver import map_url


class MapBridge(QObject):
    """Exposed to JavaScript as window.bridge."""
    route_changed = Signal(list)   # [[lat, lng], ...]

    @Slot(str)
    def onRouteChanged(self, json_str: str):
        pts = json.loads(json_str)
        self.route_changed.emit(pts)


class MapWidget(QWebEngineView):
    route_updated = Signal(list)   # propagated to main window

    def __init__(self, parent=None):
        super().__init__(parent)

        # Allow the local HTTP page to call external tile servers
        s = self.settings()
        s.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True)
        s.setAttribute(QWebEngineSettings.WebAttribute.JavascriptEnabled, True)

        self._channel = QWebChannel(self.page())
        self._bridge = MapBridge(self)
        self._channel.registerObject("bridge", self._bridge)
        self.page().setWebChannel(self._channel)

        self._bridge.route_changed.connect(self.route_updated)

        self.load(QUrl(map_url()))

    def show_track_line(self, profile):
        """
        Draw the computed alignment on the map.
        profile: ndarray (N, 4) — chainage, lat, lng, elev
        """
        pts = [[float(row[1]), float(row[2])] for row in profile]
        js = f"showTrackLine({json.dumps(pts)});"
        self.page().runJavaScript(js)

    def set_optimised_route(self, waypoints_list):
        """
        Replace current waypoints with the optimizer's result.
        waypoints_list: list of (lat, lon) tuples.
        """
        pts = [[float(lat), float(lon)] for lat, lon in waypoints_list]
        pts_json = json.dumps(pts)
        self.page().runJavaScript(f"setOptimisedRoute({json.dumps(pts_json)});")

    def remove_waypoint(self, index: int):
        self.page().runJavaScript(f"removeWaypoint({index});")

    def fit_to_route(self):
        self.page().runJavaScript("fitToRoute();")

    def load_route(self, waypoints):
        """Load a list of [lat, lng] pairs onto the map, replacing current route."""
        pts = [[float(p[0]), float(p[1])] for p in waypoints]
        pts_json = json.dumps(pts)
        self.page().runJavaScript(f"setRouteFromPython({json.dumps(pts_json)});")

    def clear_route(self):
        self.page().runJavaScript("clearRoute();")
