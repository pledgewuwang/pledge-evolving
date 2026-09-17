"""Capabilities: skills, plugins and connectors behind one contract.

Hermes, Codex, WorkBuddy and OpenClaw all converged on the same idea from
different angles — a directory *is* a capability, described by a manifest, and
trust is a property of where it came from. This module makes that one contract
instead of three, and keeps the parts they disagreed about explicit:

* ``SKILL.md`` frontmatter is the description surface (all four agree)
* installs land in a **versioned, immutable cache** (Codex)
* capabilities resolve from two anchors: the product tree, then the profile tree
* an untrusted project-local capability must be promoted with ``trust()`` before
  it can execute anything
* agent-authored capabilities carry ``provenance: agent`` and are curator-able
"""

from __future__ import annotations

import json
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)
MANIFEST_NAMES = ("forge.capability.json", "plugin.json", "SKILL.md")


def _parse_frontmatter(text: str) -> dict[str, Any]:
    match = FRONTMATTER.match(text)
    if not match:
        return {}
    out: dict[str, Any] = {}
    for line in match.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        value = value.strip().strip('"').strip("'")
        if value.startswith("[") and value.endswith("]"):
            out[key.strip()] = [v.strip().strip('"').strip("'") for v in value[1:-1].split(",") if v.strip()]
        else:
            out[key.strip()] = value
    return out


@dataclass
class Capability:
    name: str
    path: Path
    kind: str = "skill"
    version: str = "0.0.0"
    description: str = ""
    allowed_tools: tuple[str, ...] = ()
    trusted: bool = False
    provenance: str = "bundled"        # bundled | marketplace | project | agent
    source: str = ""                   # zip | git | directory
    installed_at: float = field(default_factory=time.time)
    enabled: bool = True
    meta: dict[str, Any] = field(default_factory=dict)

    def to_raw(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "version": self.version,
            "description": self.description,
            "allowed_tools": list(self.allowed_tools),
            "trusted": self.trusted,
            "provenance": self.provenance,
            "source": self.source,
            "installed_at": self.installed_at,
            "enabled": self.enabled,
            "path": str(self.path),
            "meta": self.meta,
        }

    @property
    def executable(self) -> bool:
        return self.trusted and self.enabled

    def instructions(self) -> str:
        """The text a skill injects into context when it is invoked."""
        skill_md = self.path / "SKILL.md"
        if skill_md.is_file():
            text = skill_md.read_text(encoding="utf-8", errors="replace")
            return FRONTMATTER.sub("", text, count=1).strip()
        return self.description


class CapabilityLibrary:
    """Discovery + installation + trust for all three capability kinds."""

    def __init__(self, roots: Iterable[Path], *, state_path: Path | None = None) -> None:
        self.roots = [Path(r) for r in roots]
        self.state_path = Path(state_path) if state_path else None
        self._caps: dict[str, Capability] = {}
        self.state: dict[str, Any] = {"version": 1, "enabled": {}, "trusted": {}, "archived": {}}
        if self.state_path and self.state_path.is_file():
            try:
                self.state.update(json.loads(self.state_path.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                pass

    # -- discovery -------------------------------------------------------
    def scan(self) -> list[Capability]:
        for root in self.roots:
            if not root.is_dir():
                continue
            for child in sorted(root.iterdir()):
                if not child.is_dir():
                    continue
                cap = self._load(child, root)
                if cap is not None:
                    # first anchor wins: the product tree shadows the profile tree
                    self._caps.setdefault(cap.name, cap)
        self._apply_state()
        return self.list()

    def _load(self, path: Path, root: Path) -> Capability | None:
        manifest = path / "forge.capability.json"
        meta: dict[str, Any] = {}
        if manifest.is_file():
            try:
                meta = json.loads(manifest.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                return None
        elif (path / "SKILL.md").is_file():
            meta = _parse_frontmatter((path / "SKILL.md").read_text(encoding="utf-8", errors="replace"))
        else:
            return None

        provenance = str(meta.get("provenance") or ("bundled" if "bundled" in str(root).lower() else "project"))
        return Capability(
            name=str(meta.get("name") or path.name),
            path=path,
            kind=str(meta.get("kind", "skill")),
            version=str(meta.get("version", "0.0.0")),
            description=str(meta.get("description", "")),
            allowed_tools=tuple(meta.get("allowed-tools") or meta.get("allowed_tools") or ()),
            trusted=bool(meta.get("trusted", provenance in {"bundled", "marketplace"})),
            provenance=provenance,
            source=str(meta.get("source", "directory")),
            enabled=bool(meta.get("enabled", True)),
            meta=meta,
        )

    def _apply_state(self) -> None:
        for name, cap in self._caps.items():
            if name in self.state.get("enabled", {}):
                cap.enabled = bool(self.state["enabled"][name])
            if name in self.state.get("trusted", {}):
                cap.trusted = bool(self.state["trusted"][name])

    def _save_state(self) -> None:
        if not self.state_path:
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.state, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.state_path)

    # -- api -------------------------------------------------------------
    def list(self) -> list[Capability]:
        return sorted(self._caps.values(), key=lambda c: (c.kind, c.name))

    def get(self, name: str) -> Capability | None:
        return self._caps.get(name)

    def trust(self, name: str, trusted: bool = True) -> Capability:
        cap = self._caps.get(name)
        if cap is None:
            raise KeyError(name)
        cap.trusted = trusted
        self.state.setdefault("trusted", {})[name] = trusted
        self._save_state()
        return cap

    def enable(self, name: str, enabled: bool = True) -> Capability:
        cap = self._caps.get(name)
        if cap is None:
            raise KeyError(name)
        cap.enabled = enabled
        self.state.setdefault("enabled", {})[name] = enabled
        self._save_state()
        return cap

    def install(self, source_path: Path, *, cache_root: Path, version: str,
                provenance: str = "marketplace", kind: str = "skill") -> Capability:
        """Install into a versioned, immutable cache directory."""
        source_path = Path(source_path)
        target = Path(cache_root) / source_path.name / version
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            shutil.rmtree(target)  # never write into a published version in place
        shutil.copytree(source_path, target)
        (target / "forge.capability.json").write_text(
            json.dumps(
                {
                    "name": source_path.name,
                    "kind": kind,
                    "version": version,
                    "provenance": provenance,
                    "source": "directory",
                    "trusted": provenance in {"bundled", "marketplace"},
                    "installed_at": time.time(),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        self.roots.insert(0, Path(cache_root))
        self.scan()
        return self._caps[source_path.name]

    def audit(self) -> list[dict[str, Any]]:
        """Supply-chain style audit surface: what is installed and from where."""
        return [
            {
                "name": c.name,
                "kind": c.kind,
                "version": c.version,
                "provenance": c.provenance,
                "trusted": c.trusted,
                "enabled": c.enabled,
                "executable": c.executable,
                "path": str(c.path),
            }
            for c in self.list()
        ]

    def context_injection(self) -> str:
        """One-line-per-capability index; full text loads only on invocation."""
        lines = [
            f"- {c.name} ({c.kind} v{c.version}): {c.description}"
            for c in self.list()
            if c.enabled and c.trusted
        ]
        return "\n".join(lines)


__all__ = ["Capability", "CapabilityLibrary", "MANIFEST_NAMES", "_parse_frontmatter"]
