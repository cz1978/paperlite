from paperlite.profiles import get_profile, list_profiles, load_profiles, profile_sources


def test_builtin_profiles_reuse_reader_source_sets():
    profiles = {profile.key: profile for profile in load_profiles()}

    assert profiles["mixed"].sources == ("arxiv", "biorxiv", "medrxiv", "chemrxiv", "nature", "science", "cell")
    assert profiles["preprints"].sources == ("arxiv", "biorxiv", "medrxiv", "chemrxiv")
    assert profiles["journals"].label == "顶刊"
    assert profile_sources("ai") == ["arxiv", "openalex"]
    assert profiles["chemistry"].metadata["discipline"] == "Chemistry"
    assert "chemrxiv" in profiles["chemistry"].sources
    assert profiles["materials"].label == "材料"
    assert "nature_nature_materials_aop" in profiles["materials"].sources
    assert profiles["physics"].metadata["discipline"] == "Physics"
    assert profiles["earth_science"].label == "地球科学"
    assert profiles["economics"].metadata["discipline"] == "Economics"
    assert profiles["life_science"].label == "生命科学"
    assert profiles["engineering"].metadata["discipline"] == "Engineering"
    assert profiles["multidisciplinary"].metadata["discipline"] == "Multidisciplinary"
    assert profiles["high_stability"].metadata["purpose"] == "stable-daily"


def test_external_profiles_path_from_env(tmp_path, monkeypatch):
    path = tmp_path / "profiles.yaml"
    path.write_text(
        """
profiles:
  - key: my-lab
    label: My Lab
    description: A lab-owned source mix.
    tags: ["lab", "weekly"]
    sources: arxiv,nature-medicine
    include: [pubmed, openalex, pubmed]
    exclude: [openalex]
    endpoints: [nature-medicine, pubmed]
    metadata:
      discipline: custom-biology
      owner: ada
  - key: mixed
    label: Fallback
    sources: [science]
""".strip(),
        encoding="utf-8",
    )
    monkeypatch.setenv("PAPERLITE_PROFILES_PATH", str(path))

    profile = get_profile("my-lab")
    assert profile.sources == ("arxiv", "nature-medicine", "pubmed")
    assert profile.endpoints == ("nature-medicine", "pubmed")
    assert profile.description == "A lab-owned source mix."
    assert profile.tags == ("lab", "weekly")
    assert profile.metadata["discipline"] == "custom-biology"
    assert profile.metadata["owner"] == "ada"
    assert profile.to_dict()["metadata"]["owner"] == "ada"
    assert profile.to_dict()["endpoints"] == ["nature-medicine", "pubmed"]
    assert profile_sources("my-lab") == ["arxiv", "nature-medicine", "pubmed"]
    assert get_profile("unknown").sources == ("science",)
    assert list_profiles()[0]["key"] == "my-lab"
