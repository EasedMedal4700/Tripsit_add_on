FindInsertLocation Java tool

Usage

- Compile:

  javac -d . tools/FindInsertLocation.java

- Run (example):

  java -cp . tools.FindInsertLocation Captagon drugs.json

If `javac` is not found on Windows, install a JDK and add its `bin` folder to `PATH` (for example install Temurin/Adoptium or Oracle JDK). After installation you can verify with `javac -version`.

Description

This small CLI scans `drugs.json` for top-level keys, determines a slug from the provided drug name (lowercased, non-alphanumerics replaced with `-`), and prints:
- whether the key already exists and its line number
- where to insert the new entry (previous and next top-level keys with line numbers)
- a suggested JSON snippet to paste into `drugs.json` between surrounding keys.

Notes

- The tool does not modify `drugs.json`; it only suggests an insertion point and snippet.
- Make a backup before editing the JSON and ensure trailing commas match the file's style.
