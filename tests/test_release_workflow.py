"""Tests for the release workflow.

This workflow cannot be exercised the way the rest of the pipeline is. Pushing
a version tag would publish a real release, so CI never runs it, which leaves
its shell steps untested by default. The steps that make the decisions --
which build to release, whether the tag matches the source, which files become
release assets -- are ordinary shell and are therefore run here directly,
against a synthetic artifact tree and a real tag lookup.

The rest is asserted structurally: the trigger, the permissions, and the fact
that the Build uploads what the release needs to find.
"""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
RELEASE_WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"
BUILD_WORKFLOW = ROOT / ".github" / "workflows" / "build.yml"

VERSION = "1.2.3"
REPOSITORY = "livelyfun/Smart-File-Organizer-CLI"

ASSET_TYPES = ("*.tar.xz", "*.dmg", "*.exe")


def _load(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _triggers(workflow):
    """Return a workflow's triggers.

    YAML 1.1 reads the key "on" as the boolean True, so PyYAML hands it back
    under that name. Both spellings are accepted here so the tests say what
    they mean instead of which parser quirk they are working around.
    """
    if "on" in workflow:
        return workflow["on"]
    return workflow[True]


def _step(workflow, job, name):
    for step in workflow["jobs"][job]["steps"]:
        if step.get("name") == name:
            return step
    raise AssertionError(f"no step named {name!r} in job {job!r}")


@pytest.fixture(scope="module")
def release():
    return _load(RELEASE_WORKFLOW)


@pytest.fixture(scope="module")
def build():
    return _load(BUILD_WORKFLOW)


@pytest.fixture(scope="module")
def bash():
    return shutil.which("bash") or "bash"


def _run(bash, script, env=None, cwd=None):
    """Run a workflow step's shell body, as the runner would.

    The caller's environment is inherited, because a runner's PATH is what
    makes `python` resolvable and that path is set up outside the step.
    """
    environment = dict(os.environ)
    environment.update(env or {})
    return subprocess.run(
        [bash, "-c", script],
        env=environment,
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        text=True,
    )


def test_release_follows_a_successful_build(release):
    """Releases are driven by the Build that produced the binaries.

    Rebuilding in the release workflow would publish a second set of binaries
    that never passed the build workflow's smoke test.
    """
    triggers = _triggers(release)

    assert triggers["workflow_run"]["workflows"] == ["Build"]
    assert triggers["workflow_run"]["types"] == ["completed"]


def test_release_can_be_run_by_hand(release):
    """A dry run is the only safe way to check the workflow by hand.

    Publishing is opt-in: the default is to verify and stop, so triggering it
    by accident cannot create a release.
    """
    inputs = _triggers(release)["workflow_dispatch"]["inputs"]

    assert inputs["dry_run"]["default"] is True
    assert set(inputs) == {"version", "run_id", "dry_run"}


def test_a_pull_request_build_cannot_reach_the_write_steps(release):
    """Only a pushed tag may lead to a release.

    A workflow triggered by workflow_run runs with the default branch's
    permissions, so a pull request must be refused before any step holding a
    write token, and the tag is re-derived from the repository afterwards
    rather than trusted from the event.
    """
    step = _step(release, "release", "Resolve the build and version to release")
    resolve = step["run"]

    assert '"${SOURCE_EVENT}" != "push"' in resolve
    assert "git tag --points-at" in resolve, "the tag must come from the repository, not the payload"


def test_the_triggering_run_is_passed_in_from_the_payload(release):
    """GitHub does not export the triggering run as environment variables.

    The run that fired a workflow_run event is described by
    GITHUB_WORKFLOW_REF and GITHUB_WORKFLOW_SHA, which point at this
    workflow's own file rather than the triggering run. Its id, commit and
    originating event exist only in the payload, so all three have to be
    mapped into the step. Reading an invented name fails under `set -u` with
    "unbound variable", which is how the first two live runs of this workflow
    ended.
    """
    step = _step(release, "release", "Resolve the build and version to release")

    for invented in ("GITHUB_EVENT_WORKFLOW_RUN_EVENT", "GITHUB_WORKFLOW_RUN_ID", "GITHUB_WORKFLOW_RUN_HEAD_SHA"):
        assert invented not in step["run"], f"{invented} does not exist in a runner"

    environment = step["env"]
    assert environment["SOURCE_EVENT"] == "${{ github.event.workflow_run.event }}"
    assert environment["SOURCE_RUN_ID"] == "${{ github.event.workflow_run.id }}"
    assert environment["SOURCE_SHA"] == "${{ github.event.workflow_run.head_sha }}"



def test_release_holds_only_the_permissions_it_needs(release):
    """The release job writes a release; the Pages job deploys the site.

    Nothing here needs to modify the repository contents beyond the release
    itself, and the job that deploys must not be able to create releases.
    """
    release_job = release["jobs"]["release"]["permissions"]
    pages_job = release["jobs"]["pages"]["permissions"]

    assert set(release_job) == {"contents", "actions"}
    assert release_job["contents"] == "write"
    assert release_job["actions"] == "read"

    assert set(pages_job) == {"pages", "id-token"}
    assert "contents" not in pages_job


def test_pages_failure_does_not_hide_a_published_release(release):
    """Pages needs a one-time manual setting, so its failure is survivable.

    The release is already published when this job starts. Failing the whole
    workflow afterwards would read as "the release failed" when it did not.
    """
    assert release["jobs"]["pages"]["continue-on-error"] is True


def test_the_manifest_is_only_deployed_after_a_release_was_published(release):
    """A push that released nothing must not attempt a deployment.

    Every step of the release job is skipped when there is no version tag, and
    a job whose steps were all skipped still reports success, so the Pages job
    cannot tell the difference on its own. Left ungated it runs on every push
    and fails looking for a manifest that was never written, which is noise
    that would hide a real deployment failure.
    """
    output = release["jobs"]["release"]["outputs"]["published"]

    assert "steps.target.outputs.skip" in output, (
        "the published output has to account for the skip that a tagless push takes"
    )
    assert "inputs.dry_run" in output, "a dry run publishes nothing, so it deploys nothing"
    assert release["jobs"]["pages"]["if"] == "needs.release.outputs.published == 'true'"


def test_release_takes_the_artifacts_the_build_uploaded(release, build):
    """The download pattern and the upload name have to meet.

    A pattern that matches nothing downloads nothing, and the release would
    then be created with no assets at all.
    """
    upload = _step(build, "build", "Upload executable")
    download = _step(release, "release", "Download the built artifacts")

    assert download["with"]["run-id"], "the artifacts must come from the build run"
    assert download["with"]["pattern"] == "smart-organizer-*"
    assert "smart-organizer-" in upload["with"]["name"]


def test_build_uploads_every_asset_the_release_needs(build):
    """Sidecars included: an asset without one cannot be installed.

    install.sh and install.ps1 refuse to install a download they cannot
    verify, so an uploaded artifact without its sidecar produces a release
    that no installer will use.
    """
    paths = _step(build, "build", "Upload executable")["with"]["path"]

    for suffix in (*ASSET_TYPES, "*.sha256"):
        assert f"packaging/output/{suffix}" in paths


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash is needed to run the step")
@pytest.mark.parametrize(
    "tag, expected_exit",
    [
        (None, 0),
        # A tag that does not match the version in the source would ship an
        # installer whose own --version output disagrees with the release name.
        ("v9.9.9", 1),
        # Releases are named v* everywhere, so an unprefixed tag is a mistake
        # to report rather than a version to publish.
        (VERSION, 1),
    ],
)
def test_tag_must_match_the_packaged_version(release, bash, tag, expected_exit):
    """The tag is checked against __version__ in the source being released.

    The matching tag is built from the version the package actually declares,
    so this stays correct when the version is bumped.
    """
    import smart_organizer

    if tag is None:
        tag = f"v{smart_organizer.__version__}"

    script = _step(release, "release", "Confirm the tag matches the packaged version")["run"]
    result = _run(bash, script, env={"TAG": tag}, cwd=ROOT)

    assert result.returncode == expected_exit, result.stdout + result.stderr


def _stage_downloads(root, assets):
    """Lay out a downloaded-artifact tree the way actions/download-artifact does.

    Each asset comes with its sidecar, which is what the Build uploads, so a
    test has to remove one deliberately to exercise the failure.
    """
    for index, name in enumerate(assets):
        platform = root / "downloaded" / f"smart-organizer-platform-{index}"
        # Every platform artifact also carries the raw bundle, which is not a
        # release asset and must not become one.
        (platform / "smart-organizer").mkdir(parents=True)
        (platform / "smart-organizer" / "smart-organizer").write_text("binary")
        (platform / name).write_text("artifact")
        (platform / f"{name}.sha256").write_text("digest")
    return root


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash is needed to run the step")
def test_release_assets_exclude_the_bundle_and_need_sidecars(release, bash, tmp_path):
    """Only installers and their sidecars are published.

    The onedir bundle is present in every Build artifact and is identical
    across platforms, so collecting it would attach three copies of the same
    thing to the release.
    """
    _stage_downloads(
        tmp_path,
        [
            f"smart-organizer-{VERSION}-linux-x86_64.tar.xz",
            f"SmartFileOrganizer-{VERSION}-macos.dmg",
            f"SmartFileOrganizer-{VERSION}-setup.exe",
        ],
    )

    script = _step(release, "release", "Collect the release assets")["run"]
    result = _run(
        bash,
        script,
        env={"RELEASE_RUN_ID": "1", "TAG": f"v{VERSION}", "GITHUB_REPOSITORY": REPOSITORY},
        cwd=tmp_path,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    published = sorted(path.name for path in (tmp_path / "release").iterdir())
    assert published == [
        f"SmartFileOrganizer-{VERSION}-macos.dmg",
        f"SmartFileOrganizer-{VERSION}-macos.dmg.sha256",
        f"SmartFileOrganizer-{VERSION}-setup.exe",
        f"SmartFileOrganizer-{VERSION}-setup.exe.sha256",
        f"smart-organizer-{VERSION}-linux-x86_64.tar.xz",
        f"smart-organizer-{VERSION}-linux-x86_64.tar.xz.sha256",
    ]
    assert not list((tmp_path / "release").rglob("smart-organizer"))


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash is needed to run the step")
def test_an_asset_without_a_sidecar_fails_the_release(release, bash, tmp_path):
    """An unverifiable download must not be published.

    Both installers stop on a missing or wrong checksum, so a release carrying
    such an asset is published and uninstallable.
    """
    _stage_downloads(tmp_path, [f"smart-organizer-{VERSION}-linux-x86_64.tar.xz"])
    (tmp_path / "downloaded" / "smart-organizer-platform-0"
     / f"smart-organizer-{VERSION}-linux-x86_64.tar.xz.sha256").unlink()

    script = _step(release, "release", "Collect the release assets")["run"]
    result = _run(
        bash,
        script,
        env={"RELEASE_RUN_ID": "1", "TAG": f"v{VERSION}", "GITHUB_REPOSITORY": REPOSITORY},
        cwd=tmp_path,
    )

    assert result.returncode != 0
    assert "no .sha256 sidecar" in result.stderr


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash is needed to run the step")
def test_manifest_is_kept_out_of_the_release_assets(release, bash, tmp_path):
    """latest.json is deployed to Pages, not attached to the release.

    Two copies of the manifest can disagree when the Pages deployment fails,
    and the update check is documented to read the Pages one.
    """
    _stage_downloads(tmp_path, [f"smart-organizer-{VERSION}-linux-x86_64.tar.xz"])

    script = _step(release, "release", "Collect the release assets")["run"]
    env = {"RELEASE_RUN_ID": "1", "TAG": f"v{VERSION}", "GITHUB_REPOSITORY": REPOSITORY}
    assert _run(bash, script, env=env, cwd=tmp_path).returncode == 0

    assert not (tmp_path / "release" / "latest.json").exists()
    assert (tmp_path / "manifest" / "latest.json").is_file()

    create = _step(release, "release", "Create the GitHub release")["run"]
    assert "release/*" in create
    assert "manifest" not in create


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash is needed to run the step")
def test_published_manifest_is_readable_by_the_update_check(release, bash, tmp_path):
    """The manifest is checked with the update service's own parser.

    The manifest is generated by a heredoc in a shell step, so its shape is
    only as good as that text. Parsing it the way the application does is the
    only way to notice a field renamed on one side only.
    """
    from smart_organizer.application.services.update_service import Release

    _stage_downloads(tmp_path, [f"smart-organizer-{VERSION}-linux-x86_64.tar.xz"])

    script = _step(release, "release", "Collect the release assets")["run"]
    env = {"RELEASE_RUN_ID": "1", "TAG": f"v{VERSION}", "GITHUB_REPOSITORY": REPOSITORY}
    assert _run(bash, script, env=env, cwd=tmp_path).returncode == 0

    published = Release.from_manifest(
        json.loads((tmp_path / "manifest" / "latest.json").read_text(encoding="utf-8"))
    )

    assert published.version == VERSION
    assert published.notes_url.endswith(f"/releases/tag/v{VERSION}")


def test_update_service_reads_the_manifest_the_release_publishes(release):
    """The published location is the one the application checks.

    update_service already points at GitHub Pages. A manifest published
    anywhere else, such as an asset on the release, would never be read.
    """
    from smart_organizer.application.services.update_service import DEFAULT_MANIFEST_URL

    assert "github.io" in DEFAULT_MANIFEST_URL

    upload = _step(release, "release", "Upload the manifest")
    assert upload["uses"].startswith("actions/upload-pages-artifact")
    assert upload["with"]["path"] == "manifest/latest.json"


def test_release_does_not_rebuild(release):
    """No packaging step may appear in the release workflow.

    Building here would mean releasing binaries that never passed the Build
    workflow's smoke test and checksum checks. Comments are ignored: naming
    the build script to say it is deliberately not called is not calling it.
    """
    bodies = [
        "\n".join(
            line for line in step.get("run", "").splitlines()
            if not line.lstrip().startswith("#")
        )
        for step in release["jobs"]["release"]["steps"]
    ]

    assert not any(re.search(r"packaging/build\.py|pyinstaller", body) for body in bodies)


# The environment variables GitHub documents. A name that looks like one of
# these is not automatically one: GITHUB_WORKFLOW_RUN_ID and
# GITHUB_EVENT_WORKFLOW_RUN_EVENT both read as though they existed, and both
# were invented before a live run failed on them.
GITHUB_ENVIRONMENT = {
    "CI",
    "GITHUB_ACTION",
    "GITHUB_ACTIONS",
    "GITHUB_ACTOR",
    "GITHUB_API_URL",
    "GITHUB_BASE_REF",
    "GITHUB_ENV",
    "GITHUB_EVENT_NAME",
    "GITHUB_EVENT_PATH",
    "GITHUB_GRAPHQL_URL",
    "GITHUB_HEAD_REF",
    "GITHUB_JOB",
    "GITHUB_OUTPUT",
    "GITHUB_PATH",
    "GITHUB_REF",
    "GITHUB_REF_NAME",
    "GITHUB_REF_TYPE",
    "GITHUB_REPOSITORY",
    "GITHUB_REPOSITORY_ID",
    "GITHUB_REPOSITORY_OWNER",
    "GITHUB_RETENTION_DAYS",
    "GITHUB_RUN_ATTEMPT",
    "GITHUB_RUN_ID",
    "GITHUB_RUN_NUMBER",
    "GITHUB_SERVER_URL",
    "GITHUB_SHA",
    "GITHUB_STEP_SUMMARY",
    "GITHUB_TRIGGERING_ACTOR",
    "GITHUB_WORKFLOW",
    "GITHUB_WORKFLOW_REF",
    "GITHUB_WORKFLOW_SHA",
    "GITHUB_WORKSPACE",
    "RUNNER_ARCH",
    "RUNNER_NAME",
    "RUNNER_OS",
    "RUNNER_TEMP",
    "RUNNER_TOOL_CACHE",
}


def _code(script):
    """The script without its comments, which cannot read anything."""
    return "\n".join(line for line in script.splitlines() if not line.lstrip().startswith("#"))


def _variables_read_by(script):
    """Every name the script expands."""
    body = _code(script)
    braced = set(re.findall(r"\$\{([A-Za-z_][A-Za-z0-9_]*)", body))
    bare = set(re.findall(r"\$([A-Za-z_][A-Za-z0-9_]*)", body))
    return braced | bare


def _variables_assigned_by(script):
    """Every name the script sets itself, which needs no environment."""
    body = _code(script)
    assigned = set(
        re.findall(r"^\s*(?:local\s+|export\s+)?([A-Za-z_][A-Za-z0-9_]*)=", body, re.M)
    )
    loops = set(re.findall(r"^\s*for\s+([A-Za-z_][A-Za-z0-9_]*)\s+in\b", body, re.M))
    return assigned | loops


def _nested_programs(script):
    """Shell programs the step hands to a nested `bash -c`.

    A name expanded inside one of those is the nested shell's variable, not the
    step's, so it is checked against whatever that program sources.
    """
    return re.findall(r"bash -c '(.*?)'", _code(script), re.S)


def _sourced_paths(script):
    """The files the step sources, and so can read variables from."""
    # Stops at whitespace or a command separator, so "source a.sh; next" does
    # not yield the path "a.sh;".
    return re.findall(r"^\s*source\s+([^\s;]+)", _code(script), re.M)


@pytest.mark.parametrize("workflow_name", ["release", "build"])
def test_every_variable_a_step_reads_is_one_it_can_actually_have(workflow_name):
    """A step may not read a variable that nothing provides.

    A structural test cannot tell an invented GITHUB_ name from a real one,
    which is how two made-up names reached a live run. What can be checked is
    arithmetic: each expanded name must be defined by the step's own env,
    assigned by the step, or documented by GitHub. Anything else fails the
    step under `set -u`.
    """
    workflow = _load(ROOT / ".github" / "workflows" / f"{workflow_name}.yml")
    unreadable = []

    for job_name, job in workflow["jobs"].items():
        for step in job["steps"]:
            script = step.get("run")
            if not script:
                continue
            available = (
                set(step.get("env", {})) | _variables_assigned_by(script) | GITHUB_ENVIRONMENT
            )
            # Nested payloads are blanked out first: a name inside a quoted
            # `bash -c` program is the nested shell's, not the step's.
            own = re.sub(r"bash -c '[^']*'", "", script, flags=re.S)
            for name in _variables_read_by(own):
                if name not in available:
                    unreadable.append(
                        f"{workflow_name}.yml {job_name} / {step.get('name')}: ${{{name}}}"
                    )

            # A nested `bash -c` has its own variables, provided by whatever it
            # sources, and only the names that program itself expands need
            # resolving. The rest of the sourced file is that script's business.
            for program in _nested_programs(script):
                sourced = ""
                for path in _sourced_paths(program):
                    candidate = ROOT / path
                    if candidate.is_file():
                        sourced += candidate.read_text(encoding="utf-8")
                provided = available | _variables_assigned_by(sourced)
                for name in _variables_read_by(program):
                    if name not in provided:
                        unreadable.append(
                            f"{workflow_name}.yml {job_name} / {step.get('name')}: "
                            f"nested ${{{name}}}"
                        )

    assert not unreadable, (
        "these are read but never provided, so the step fails under set -u: "
        + "; ".join(unreadable)
    )
