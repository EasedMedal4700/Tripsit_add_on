using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;
using System.Text.Json.Nodes;

class Program
{
    static void Main(string[] args)
    {
        string drugsJsonPath = @"c:\Users\USER\dev\code\drugs-tripsit\drugs.json";
        string extractedDosesPath = @"c:\Users\USER\dev\code\drugs-tripsit\tools\data\extracted_doses.json";

        // Read drugs.json
        string drugsJsonText = File.ReadAllText(drugsJsonPath);
        using JsonDocument drugsDoc = JsonDocument.Parse(drugsJsonText);
        List<string> orderedPrettyNames = new List<string>();
        foreach (var property in drugsDoc.RootElement.EnumerateObject())
        {
            if (property.Value.TryGetProperty("pretty_name", out JsonElement prettyNameElement))
            {
                orderedPrettyNames.Add(prettyNameElement.GetString()!);
            }
        }

        // Read extracted_doses.json
        string extractedJsonText = File.ReadAllText(extractedDosesPath);
        JsonNode extractedNode = JsonNode.Parse(extractedJsonText)!;

        // Create a new JsonObject
        JsonObject reorderedJson = new JsonObject();
        foreach (string prettyName in orderedPrettyNames)
        {
            if (extractedNode[prettyName] != null)
            {
                reorderedJson[prettyName] = extractedNode[prettyName]!.DeepClone();
            }
        }

        // Write back
        var options = new JsonSerializerOptions { WriteIndented = true, Encoder = System.Text.Encodings.Web.JavaScriptEncoder.UnsafeRelaxedJsonEscaping };
        string output = reorderedJson.ToJsonString(options);
        File.WriteAllText(extractedDosesPath, output);
        Console.WriteLine("Extracted doses JSON has been reordered to match the order in drugs.json.");
    }
}