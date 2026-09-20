using System.Text.Json;
using OpenRGBTempSync.SensorBridge;
using Xunit;

namespace OpenRGBTempSync.SensorBridge.Tests
{
    public class SensorProtocolTests
    {
        [Fact]
        public void SerializeHello_ReturnsExpectedJson()
        {
            string json = SensorProtocol.SerializeHello("1.0.0", "0.9.6", 4567, 1000);
            using var doc = JsonDocument.Parse(json);
            var root = doc.RootElement;

            Assert.Equal(1, root.GetProperty("schema").GetInt32());
            Assert.Equal("hello", root.GetProperty("type").GetString());
            Assert.Equal("1.0.0", root.GetProperty("bridge_version").GetString());
            Assert.Equal(4567, root.GetProperty("pid").GetInt32());
            Assert.Equal(1000, root.GetProperty("interval_ms").GetInt32());
        }

        [Fact]
        public void SerializeSample_ReturnsExpectedJson()
        {
            string json = SensorProtocol.SerializeSample(
                42, 55.5f, 62.0f, "AMD Ryzen / Core", "NVIDIA RTX / Core", new() { "Warning 1" }
            );
            using var doc = JsonDocument.Parse(json);
            var root = doc.RootElement;

            Assert.Equal(1, root.GetProperty("schema").GetInt32());
            Assert.Equal("sample", root.GetProperty("type").GetString());
            Assert.Equal(42, root.GetProperty("seq").GetInt64());
            Assert.Equal(55.5f, root.GetProperty("cpu_c").GetSingle());
            Assert.Equal(62.0f, root.GetProperty("gpu_c").GetSingle());
            Assert.Equal("AMD Ryzen / Core", root.GetProperty("cpu_source").GetString());
        }

        [Fact]
        public void SerializeFatal_ReturnsExpectedJson()
        {
            string json = SensorProtocol.SerializeFatal(30, "No sensor");
            using var doc = JsonDocument.Parse(json);
            var root = doc.RootElement;

            Assert.Equal(1, root.GetProperty("schema").GetInt32());
            Assert.Equal("fatal", root.GetProperty("type").GetString());
            Assert.Equal(30, root.GetProperty("code").GetInt32());
            Assert.Equal("No sensor", root.GetProperty("message").GetString());
        }
    }
}