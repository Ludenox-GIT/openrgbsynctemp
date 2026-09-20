using System.Collections.Generic;
using LibreHardwareMonitor.Hardware;
using OpenRGBTempSync.SensorBridge;
using Xunit;

namespace OpenRGBTempSync.SensorBridge.Tests
{
    public class SensorSelectorTests
    {
        [Fact]
        public void SelectCpuSensor_EmptyHardwareList_ReturnsNull()
        {
            var result = SensorSelector.SelectCpuSensor(new List<IHardware>());
            Assert.Null(result);
        }

        [Fact]
        public void SelectGpuSensor_EmptyHardwareList_ReturnsNull()
        {
            var result = SensorSelector.SelectGpuSensor(new List<IHardware>());
            Assert.Null(result);
        }
    }
}