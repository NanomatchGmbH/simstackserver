"""Upload manifest for WaNo and workflow submissions.

Provides a structured answer to the question "what do I need to provide before
submitting?" by classifying every file a WaNo requires into one of two categories:

* ``wano_definition`` — WaNo XML, configuration, and static input files.  These
  are generated automatically by :meth:`~WaNoModels.WaNoModelRoot.prepare_files_submission`
  and require no manual action from the user.

* ``external_input`` — scientific data files that the user must supply.  These
  correspond to ``WaNoItemFileModel`` entries that carry a local-file flag.  If the
  local source path is not set or the file does not exist the submission will fail.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class UploadItem:
    """Describes a single file that must be present on the server before job execution.

    Attributes
    ----------
    server_path:
        Path on the server relative to ``storage``, e.g.
        ``workflow_data/Step1/inputs/molecule.xyz``.
    logical_name:
        Filename as seen inside the job execution directory.
    wfem_name:
        Name of the WaNo that requires this file.
    wfem_path:
        Path of the WaNo node inside the workflow, e.g. ``Step1`` or
        ``ForEach/0/Step1``.
    category:
        ``"wano_definition"`` if the file is part of the WaNo definition and is
        handled automatically by the submission pipeline.
        ``"external_input"`` if the user must supply it manually.
    local_source:
        Local filesystem path from which the file will be (or was) copied.
        ``None`` when unknown or not yet set.
    required:
        ``True`` if the job cannot run without this file.
    """

    server_path: str
    logical_name: str
    wfem_name: str
    wfem_path: str
    category: str  # "wano_definition" | "external_input"
    local_source: Optional[str] = None
    required: bool = True

    @property
    def is_wano_definition(self) -> bool:
        return self.category == "wano_definition"

    @property
    def is_external_input(self) -> bool:
        return self.category == "external_input"

    @property
    def local_source_exists(self) -> bool:
        """Return True if ``local_source`` is set and the file exists on disk."""
        return self.local_source is not None and os.path.isfile(self.local_source)


class WorkflowUploadManifest:
    """Aggregated upload manifest for an entire workflow.

    Collects :class:`UploadItem` entries from all WaNo nodes and provides
    filtered views that answer specific questions.

    Usage::

        from SimStackServer.WaNo.upload_manifest import WorkflowUploadManifest
        from SimStackServer.WaNo.WaNoModels import WaNoModelRoot

        manifest = WorkflowUploadManifest()
        for wmr, wfem_path in [(wmr_step1, "Step1"), (wmr_step2, "Step2")]:
            manifest.add_wano(wmr, wfem_path)

        # What the user must provide
        for item in manifest.required_user_uploads():
            print(item.logical_name, "->", item.server_path)

        # Validate that all local sources exist
        missing = manifest.missing_local_sources()
        if missing:
            raise RuntimeError(f"Missing files: {[i.logical_name for i in missing]}")
    """

    def __init__(self) -> None:
        self._items: List[UploadItem] = []

    def add_wano(self, wmr: "WaNoModelRoot", wfem_path: str) -> None:  # noqa: F821
        """Collect upload items from *wmr* placed at *wfem_path* in the workflow."""
        self._items.extend(wmr.get_upload_manifest(wfem_path))

    def add_item(self, item: UploadItem) -> None:
        self._items.append(item)

    # ------------------------------------------------------------------
    # Filtered views
    # ------------------------------------------------------------------

    def all_items(self) -> List[UploadItem]:
        """Return every upload item (WaNo-definition and external)."""
        return list(self._items)

    def required_user_uploads(self) -> List[UploadItem]:
        """Return only files the user must supply (``external_input`` category).

        These are the only items that can block a submission if missing.
        WaNo-definition files are generated automatically and are not included.
        """
        return [i for i in self._items if i.is_external_input]

    def wano_definition_items(self) -> List[UploadItem]:
        """Return files that are handled automatically by the submission pipeline."""
        return [i for i in self._items if i.is_wano_definition]

    def missing_local_sources(self) -> List[UploadItem]:
        """Return ``external_input`` items whose local source is missing or unset."""
        return [
            i for i in self._items if i.is_external_input and not i.local_source_exists
        ]

    def validate(self) -> None:
        """Raise :class:`FileNotFoundError` if any required external file is missing.

        Only ``external_input`` items are checked; ``wano_definition`` items are
        always auto-generated and not validated here.
        """
        missing = self.missing_local_sources()
        if missing:
            lines = "\n".join(
                f"  [{i.wfem_path}] {i.logical_name}"
                + (
                    f" (expected at: {i.local_source})"
                    if i.local_source
                    else " (no path set)"
                )
                for i in missing
            )
            raise FileNotFoundError(
                f"The following external input files are missing before workflow submission:\n{lines}"
            )

    def summary(self) -> str:
        """Return a human-readable summary of the manifest."""
        ext = self.required_user_uploads()
        defn = self.wano_definition_items()
        lines = [
            f"Workflow upload manifest: {len(self._items)} total items",
            f"  {len(defn)} wano_definition file(s) — handled automatically",
            f"  {len(ext)} external_input file(s) — must be provided by user",
        ]
        if ext:
            lines.append("")
            lines.append("Files YOU must provide:")
            for item in ext:
                status = "OK" if item.local_source_exists else "MISSING"
                src = item.local_source or "<not set>"
                lines.append(
                    f"  [{status}] {item.wfem_path}/{item.logical_name}"
                    f"\n         local: {src}"
                    f"\n         server: {item.server_path}"
                )
        return "\n".join(lines)
