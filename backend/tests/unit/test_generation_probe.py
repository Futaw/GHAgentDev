from backend.scripts.verify_generation_sandbox import assess_probes


def evidence():
    rows = {
        name: {"status": "error", "errno": 1}
        for name in (
            "sibling",
            "outside",
            "auth_sentinel",
            "update",
            "create",
            "delete",
            "rename",
            "git_write",
            "loopback",
            "public",
        )
    }
    rows["allowed"] = {"status": "read", "sha256": "expected"}
    return rows


def test_empty_or_boolean_claims_never_pass():
    for observed in ({}, {"safe": True}, [], None):
        assert all(
            value["status"] == "inconclusive"
            for value in assess_probes(observed, "expected", True).values()
        )


def test_controls_and_explicit_os_denials_are_required():
    observed = evidence()
    assert all(
        value["status"] == "passed" for value in assess_probes(observed, "expected", True).values()
    )
    assert assess_probes(observed, "expected", False)["command_network"]["status"] == "inconclusive"
    observed["public"]["errno"] = 60  # ETIMEDOUT is not permission denial.
    assert assess_probes(observed, "expected", True)["command_network"]["status"] == "inconclusive"
    observed["sibling"] = {"status": "read", "sha256": "secret"}
    assert assess_probes(observed, "expected", True)["sandbox_read"]["status"] == "failed"
    observed["delete"] = {"status": "changed"}
    assert assess_probes(observed, "expected", True)["non_modification"]["status"] == "failed"
