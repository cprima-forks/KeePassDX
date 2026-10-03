"""The object repository: many systems, each with screens, each with elements, elements nested.

    from ui import ui
    ui.find(root, "keepassdx.search.field")                  # the node, or None
    ui.require(root, "keepassdx.credentials.unlock")         # the node, or ElementMissing naming it
    ui.find_all(root, "keepassdx.search.results.title")      # a child: only inside its parent
    ui.find(root, "android.dialog.panel.positive")           # the button inside a dialog
    ui.find(root, "keepassdx.search.results.row.title", under=row)   # inside one given row
    ui.find(root, "dialer.main.number")                      # a role: the dialer of this phone

A name is `system.screen.element[.child...]`. The first part is a system (an app or a part of the
platform) or a role (dialer, browser, mailer, sms) that is bound to a system at run time from the apps
detected on the phone.

Files: every `repository/*.json` and every `environments/<environment>/*.json` is one system:

    { "system": "keepassdx", "kind": "app | platform | default-app", "package": "com.example", "role": "dialer",
      "provenance": { ... where the locators come from ... },
      "screens": { "<screen>": { "elements": { "<element>": { <locator>, "children": { ... } } } } } }

A locator can have `id` (resource id; a suffix, or the whole id when it has a colon), `desc`, `text`,
`class`, `package`, and `from: library` for an element that is not in the app's own source. A system
with a package limits its elements to that package (a prefix for an app).
"""

import json
import xml.etree.ElementTree as ET
from pathlib import Path

from errors import ElementMissing

HERE = Path(__file__).parent
REPOSITORY = HERE / "repository"

# which of the detected apps (device.detect_handlers) fills which role
ROLE_SOURCES = {
    "dialer": ("dial", "dialer-role"),
    "browser": ("web", "browser-role"),
    "mailer": ("mail",),
    "sms": ("sms-role",),
}


class Repository:
    def __init__(self) -> None:
        self.systems: dict[str, dict] = {}
        self.roles: dict[str, str] = {}  # role -> system name
        self.unbound: dict[str, str] = {}  # role -> the detected package that has no system file

    # --- loading -------------------------------------------------------------------------------
    def add(self, data: dict) -> None:
        self.systems[data["system"]] = data

    def load_folder(self, folder: Path) -> None:
        for path in sorted(folder.glob("*.json")):
            if path.name.startswith("inventory-"):
                continue  # generated inventories of the app source are not systems
            data = json.loads(path.read_text(encoding="utf-8"))
            if "system" in data:  # other files in the folder (the predicted needs) are not systems
                self.add(data)

    def bind_roles(self, detected: dict[str, str]) -> dict[str, str]:
        """Fill the roles from the apps detected on the phone: the system whose package it is."""
        self.roles.clear()
        self.unbound.clear()
        by_package = {s["package"]: name for name, s in self.systems.items() if s.get("package")}
        for role, keys in ROLE_SOURCES.items():
            package = next((detected[k] for k in keys if k in detected), None)
            if package is None:
                continue
            if package in by_package:
                self.roles[role] = by_package[package]
            else:
                self.unbound[role] = package
        return dict(self.roles)

    # --- resolving a name ----------------------------------------------------------------------
    def _chain(self, path: str) -> tuple[dict, list[dict]]:
        parts = path.split(".")
        if len(parts) < 3:
            raise KeyError(f"{path!r}: a name is system.screen.element[.child...]")
        system_name = self.roles.get(parts[0], parts[0])
        if parts[0] in self.unbound:
            raise ElementMissing(f"{path!r}: the {parts[0]} of this phone is {self.unbound[parts[0]]}, which has no "
                                 f"system file in the repository")
        if system_name not in self.systems:
            raise KeyError(f"{path!r}: no system {system_name!r} in the object repository (known: {sorted(self.systems)})")
        system = self.systems[system_name]
        try:
            locator = system["screens"][parts[1]]["elements"][parts[2]]
            chain = [locator]
            for child in parts[3:]:
                locator = locator["children"][child]
                chain.append(locator)
        except KeyError:
            raise KeyError(f"no element {path!r} in the object repository") from None
        return system, chain

    def locator(self, path: str) -> dict:
        return self._chain(path)[1][-1]

    @staticmethod
    def _matches(node: ET.Element, loc: dict, system: dict) -> bool:
        package = loc.get("package") or system.get("package")
        if package:
            actual = node.get("package", "")
            if loc.get("package"):
                if actual != package:
                    return False
            elif system.get("kind") == "app":
                if not actual.startswith(package):
                    return False
            elif actual != package:
                return False
        if "id" in loc:
            ident, rid = loc["id"], node.get("resource-id", "")
            # a full id (with a colon) must match whole; a short id matches the part after the slash of
            # `package:id/name`, or a bare name: a Compose test tag has no package and no slash
            if not (rid == ident if ":" in ident else (rid == ident or rid.endswith("/" + ident))):
                return False
        if "desc" in loc and node.get("content-desc") != loc["desc"]:
            return False
        if "text" in loc and node.get("text") != loc["text"]:
            return False
        if "class" in loc and not node.get("class", "").endswith(loc["class"]):
            return False
        if "clickable" in loc and (node.get("clickable") == "true") != loc["clickable"]:
            return False
        return True

    # --- finding -------------------------------------------------------------------------------
    def find_all(self, root: ET.Element, path: str, under: ET.Element | None = None) -> list[ET.Element]:
        """Every node of the element. A child is searched only inside the nodes of its parent; with
        `under`, only inside that one node (the parents are not looked for)."""
        system, chain = self._chain(path)
        if under is not None:
            scopes, steps = [under], chain[-1:]
        else:
            scopes, steps = [root], chain
        found: list[ET.Element] = []
        for loc in steps:
            found = []
            for scope in scopes:
                for node in scope.iter("node"):
                    if node is not scope and self._matches(node, loc, system) and node not in found:
                        found.append(node)
            scopes = found
        return found

    def find(self, root: ET.Element, path: str, under: ET.Element | None = None) -> ET.Element | None:
        hits = self.find_all(root, path, under)
        return hits[0] if hits else None

    def require(self, root: ET.Element, path: str, under: ET.Element | None = None) -> ET.Element:
        node = self.find(root, path, under)
        if node is None:
            raise ElementMissing(f"the element {path!r} ({self.locator(path)}) is not on the screen")
        return node

    @staticmethod
    def value_after_label(root: ET.Element, label: str) -> ET.Element | None:
        """A field of the entry view comes from a template: its label is a text node, its value the
        next text node. The label is the locator."""
        nodes = list(root.iter("node"))
        for i, n in enumerate(nodes):
            if n.get("class", "").endswith("TextView") and n.get("text", "").strip() == label:
                for m in nodes[i + 1:]:
                    if m.get("class", "").endswith("TextView") and m.get("text"):
                        return m
        return None


def load() -> Repository:
    repo = Repository()
    repo.load_folder(REPOSITORY)
    return repo


ui = load()
