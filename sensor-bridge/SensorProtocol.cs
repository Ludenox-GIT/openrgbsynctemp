using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace OpenRGBTempSync.SensorBridge
{
    public record HelloRecord(
        [property: JsonPropertyName("schema")] int Schema,
        [property: JsonPropertyName("type")] string Type,
        [property: JsonPropertyName("bridge_version")] string BridgeVersion,
        [property: JsonPropertyName("library_version")] string LibraryVersion,
        [property: JsonPropertyName("pid")] int Pid,
        [property: JsonPropertyName("interval_ms")] int IntervalMs
    );

    public record SampleRecord(
        [property: JsonPropertyName("schema")] int Schema,
        [property: JsonPropertyName("type")] string Type,
        [property: JsonPropertyName("seq")] long Seq,
        [property: JsonPropertyName("timestamp_utc")] string TimestampUtc,
        [property: JsonPropertyName("cpu_c")] float? CpuC,
        [property: JsonPropertyName("gpu_c")] float? GpuC,
        [property: JsonPropertyName("cpu_source")] string CpuSource,
        [property: JsonPropertyName("gpu_source")] string GpuSource,
        [property: JsonPropertyName("warnings")] List<string> Warnings
    );

    public record FatalRecord(
        [property: JsonPropertyName("schema")] int Schema,
        [property: JsonPropertyName("type")] string Type,
        [property: JsonPropertyName("code")] int Code,
        [property: JsonPropertyName("message")] string Message
    );

    public static class SensorProtocol
    {
        private static readonly JsonSerializerOptions JsonOptions = new()
        {
            DefaultIgnoreCondition = JsonIgnoreCondition.Never
        };

        public static string SerializeHello(string bridgeVersion, string libraryVersion, int pid, int intervalMs)
        {
            var record = new HelloRecord(1, "hello", bridgeVersion, libraryVersion, pid, intervalMs);
            return JsonSerializer.Serialize(record, JsonOptions);
        }

        public static string SerializeSample(long seq, float? cpuC, float? gpuC, string cpuSource, string gpuSource, List<string> warnings)
        {
            var record = new SampleRecord(
                1,
                "sample",
                seq,
                DateTime.UtcNow.ToString("o"),
                cpuC,
                gpuC,
                cpuSource,
                gpuSource,
                warnings
            );
            return JsonSerializer.Serialize(record, JsonOptions);
        }

        public static string SerializeFatal(int code, string message)
        {
            var record = new FatalRecord(1, "fatal", code, message);
            return JsonSerializer.Serialize(record, JsonOptions);
        }
    }
}