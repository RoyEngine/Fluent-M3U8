# coding: utf-8
from __future__ import annotations

from dataclasses import dataclass, field
from json import loads
from pathlib import Path
from typing import Dict, Iterable, List
import zipfile


@dataclass
class LocalizationVariant:
    name: str
    archive_path: str
    content: str


@dataclass
class JarLocalizationSource:
    jar_path: Path
    metadata: Dict
    variants: List[LocalizationVariant] = field(default_factory=list)

    @property
    def display_name(self) -> str:
        if not self.metadata:
            return self.jar_path.stem

        for key in ("name", "modid", "displayName"):
            if key in self.metadata and self.metadata[key]:
                return str(self.metadata[key])
        return self.jar_path.stem


class LocalizationService:
    """Utility helpers for inspecting localization jars."""

    @staticmethod
    def collect_sources(paths: Iterable[Path]) -> List[JarLocalizationSource]:
        jars: List[Path] = []

        for path in paths:
            if path.is_file() and path.suffix.lower() == ".jar":
                jars.append(path)
            elif path.is_dir():
                jars.extend(sorted(path.glob("**/*.jar")))

        sources: List[JarLocalizationSource] = []
        for jar_path in jars:
            metadata = LocalizationService._load_metadata(jar_path)
            variants = LocalizationService._load_variants(jar_path, metadata)
            sources.append(JarLocalizationSource(jar_path=jar_path, metadata=metadata, variants=variants))

        return sources

    @staticmethod
    def repack_with_translations(source: JarLocalizationSource, target_dir: Path, updates: Dict[str, str]) -> Path:
        target_dir.mkdir(parents=True, exist_ok=True)
        output_path = target_dir / source.jar_path.name

        with zipfile.ZipFile(source.jar_path, "r") as src_zip:
            with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as dest_zip:
                for item in src_zip.infolist():
                    if item.filename in updates:
                        dest_zip.writestr(item, updates[item.filename])
                    else:
                        dest_zip.writestr(item, src_zip.read(item.filename))

        return output_path

    @staticmethod
    def _load_metadata(jar_path: Path) -> Dict:
        with zipfile.ZipFile(jar_path, "r") as jar_file:
            for candidate in ("mod_info.json", "META-INF/mod_info.json"):
                try:
                    with jar_file.open(candidate) as fp:
                        return loads(fp.read().decode("utf-8"))
                except KeyError:
                    continue
                except Exception:
                    return {}
        return {}

    @staticmethod
    def _load_variants(jar_path: Path, metadata: Dict) -> List[LocalizationVariant]:
        variants: List[LocalizationVariant] = []
        with zipfile.ZipFile(jar_path, "r") as jar_file:
            for name in jar_file.namelist():
                if name.lower().endswith(".json") and "lang" in name.lower():
                    try:
                        content = jar_file.read(name).decode("utf-8")
                    except Exception:
                        continue

                    variants.append(
                        LocalizationVariant(
                            name=LocalizationService._format_variant_label(name, metadata),
                            archive_path=name,
                            content=content,
                        )
                    )
        return variants

    @staticmethod
    def _format_variant_label(path: str, metadata: Dict) -> str:
        base_name = Path(path).name
        mod_name = None
        for key in ("name", "modid", "displayName"):
            if key in metadata:
                mod_name = metadata.get(key)
                break

        if mod_name:
            return f"{mod_name} · {base_name}"
        return base_name
