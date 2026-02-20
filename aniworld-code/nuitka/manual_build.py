import subprocess


def build():
    # Include browsers.jsonl from fake_useragent package
    # JSON_PATH = os.path.join(
    #    os.path.dirname(fake_useragent.__file__), "data", "browsers.jsonl"
    # )

    subprocess.run(
        [
            "python",
            "-m",
            "nuitka",
            "src/aniworld",
            # "--include-data-file=" + JSON_PATH + "=fake_useragent/data/browsers.jsonl",
        ]
    )


if __name__ == "__main__":
    build()
