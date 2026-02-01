package tools;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.text.Normalizer;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

public class FindInsertLocation {
    public static void main(String[] args) throws Exception {
        if (args.length == 0) {
            System.out.println("Usage: java FindInsertLocation <Drug Name> [drugs.json path]");
            System.exit(1);
        }

        String drugName = args[0];
        String jsonPath = args.length > 1 ? args[1] : "drugs.json";

        Path path = Paths.get(jsonPath);
        if (!Files.exists(path)) {
            System.err.println("drugs.json not found at: " + path.toAbsolutePath());
            System.exit(2);
        }

        List<String> lines = Files.readAllLines(path);

        // Collect top-level keys and their start line numbers
        List<KeyPos> keys = new ArrayList<>();
        for (int i = 0; i < lines.size(); i++) {
            String line = lines.get(i);
            String trimmed = line.trim();
            if (trimmed.startsWith("\"") && trimmed.contains("\":") && trimmed.endsWith("{")) {
                // match lines like:   "key": {
                int firstQuote = trimmed.indexOf('"');
                int secondQuote = trimmed.indexOf('"', firstQuote + 1);
                if (firstQuote >= 0 && secondQuote > firstQuote) {
                    String key = trimmed.substring(firstQuote + 1, secondQuote);
                    keys.add(new KeyPos(key, i + 1)); // 1-based line
                }
            }
        }

        if (keys.isEmpty()) {
            System.err.println("No top-level keys found in " + jsonPath);
            System.exit(3);
        }

        // Sort keys lexicographically to be safe (file may already be sorted)
        keys.sort(Comparator.comparing(k -> k.key));

        String slug = slugify(drugName);

        // Check if exists
        for (KeyPos kp : keys) {
            if (kp.key.equals(slug)) {
                System.out.println("Found existing key '" + kp.key + "' at line " + kp.line + " in " + jsonPath);
                System.exit(0);
            }
        }

        // Find insertion index
        int insertIndex = 0;
        while (insertIndex < keys.size() && keys.get(insertIndex).key.compareTo(slug) < 0) {
            insertIndex++;
        }

        KeyPos prev = insertIndex - 1 >= 0 ? keys.get(insertIndex - 1) : null;
        KeyPos next = insertIndex < keys.size() ? keys.get(insertIndex) : null;

        System.out.println("Suggested slug: '" + slug + "' (derived from '" + drugName + "')");
        if (prev != null) {
            System.out.println("Insert after: '" + prev.key + "' (line " + prev.line + ")");
        } else {
            System.out.println("Insert at start of file (before: '" + next.key + "' at line " + next.line + ")");
        }
        if (next != null) {
            System.out.println("Insert before: '" + next.key + "' (line " + next.line + ")");
        } else {
            System.out.println("Insert at end of file (after: '" + prev.key + "' at line " + prev.line + ")");
        }

        System.out.println();
        System.out.println("Suggested JSON snippet (drop this between the surrounding keys, include trailing comma if needed):");
        System.out.println();
        System.out.println(generateSnippet(slug, drugName));
    }

    static String generateSnippet(String slug, String prettyName) {
        StringBuilder sb = new StringBuilder();
        sb.append("  \"").append(slug).append("\": {\n");
        sb.append("    \"aliases\": [\"" + slug + "\"],\n");
        sb.append("    \"categories\": [\"stimulant\"],\n");
        sb.append("    \"name\": \"").append(slug).append("\",\n");
        sb.append("    \"pretty_name\": \"").append(prettyName).append("\",\n");
        sb.append("    \"properties\": {\n");
        sb.append("      \"summary\": \"Add a short summary here.\"\n");
        sb.append("    }\n");
        sb.append("  },");
        return sb.toString();
    }

    static String slugify(String input) {
        String nowhitespace = input.trim().toLowerCase();
        String normalized = Normalizer.normalize(nowhitespace, Normalizer.Form.NFKD);
        // remove diacritics
        normalized = normalized.replaceAll("\\p{M}", "");
        // replace non-alnum with hyphen
        normalized = normalized.replaceAll("[^a-z0-9]+", "-");
        // collapse hyphens
        normalized = normalized.replaceAll("-+", "-");
        // trim hyphens
        if (normalized.startsWith("-")) normalized = normalized.substring(1);
        if (normalized.endsWith("-")) normalized = normalized.substring(0, normalized.length() - 1);
        return normalized;
    }

    static class KeyPos {
        String key;
        int line;

        KeyPos(String key, int line) {
            this.key = key;
            this.line = line;
        }
    }
}
