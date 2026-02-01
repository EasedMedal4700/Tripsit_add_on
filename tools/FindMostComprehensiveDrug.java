package tools;
import com.google.gson.Gson;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import java.io.FileReader;
import java.io.IOException;
import java.util.Map;

public class FindMostComprehensiveDrug {
    public static void main(String[] args) {
        Gson gson = new Gson();
        try {
            // Read the drugs.json file
            FileReader reader = new FileReader("drugs.json");
            JsonObject drugs = JsonParser.parseReader(reader).getAsJsonObject();

            String mostComprehensiveDrug = null;
            int maxCount = 0;

            for (Map.Entry<String, JsonElement> entry : drugs.entrySet()) {
                String drugName = entry.getKey();
                JsonObject drug = entry.getValue().getAsJsonObject();

                int count = countNonEmptyFields(drug);
                if (count > maxCount) {
                    maxCount = count;
                    mostComprehensiveDrug = drugName;
                }
            }

            System.out.println("Most comprehensive drug: " + mostComprehensiveDrug + " with " + maxCount + " filled fields.");

        } catch (IOException e) {
            e.printStackTrace();
        }
    }

    private static int countNonEmptyFields(JsonObject obj) {
        int count = 0;
        for (Map.Entry<String, JsonElement> entry : obj.entrySet()) {
            String key = entry.getKey();
            if ("combos".equals(key)) {
                continue; // Exclude combos from count
            }
            JsonElement value = entry.getValue();
            if (isNonEmpty(value)) {
                count++;
            }
        }
        return count;
    }

    private static boolean isNonEmpty(JsonElement element) {
        if (element.isJsonNull()) {
            return false;
        }
        if (element.isJsonPrimitive()) {
            if (element.getAsJsonPrimitive().isString()) {
                return !element.getAsString().trim().isEmpty();
            }
            return true; // numbers, booleans
        }
        if (element.isJsonArray()) {
            return element.getAsJsonArray().size() > 0;
        }
        if (element.isJsonObject()) {
            return !element.getAsJsonObject().entrySet().isEmpty();
        }
        return false;
    }
}