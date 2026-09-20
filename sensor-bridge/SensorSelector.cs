using System;
using System.Collections.Generic;
using System.Linq;
using LibreHardwareMonitor.Hardware;

namespace OpenRGBTempSync.SensorBridge
{
    public record SelectedSensor(ISensor Sensor, string SourceName);

    public static class SensorSelector
    {
        public static SelectedSensor? SelectCpuSensor(IEnumerable<IHardware> hardwareList, string? preferredIdentifier = null)
        {
            var cpuHardware = hardwareList.FirstOrDefault(h => h.HardwareType == HardwareType.Cpu);
            if (cpuHardware == null) return null;

            var tempSensors = cpuHardware.Sensors
                .Where(s => s.SensorType == SensorType.Temperature)
                .ToList();

            if (tempSensors.Count == 0) return null;

            // 1. Preferred identifier
            if (!string.IsNullOrEmpty(preferredIdentifier))
            {
                var match = tempSensors.FirstOrDefault(s => s.Identifier.ToString().Equals(preferredIdentifier, StringComparison.OrdinalIgnoreCase));
                if (match != null) return new SelectedSensor(match, $"{cpuHardware.Name} / {match.Name}");
            }

            // 2. Exact normalized "Core (Tctl/Tdie)"
            var tctl = tempSensors.FirstOrDefault(s => s.Name.Equals("Core (Tctl/Tdie)", StringComparison.OrdinalIgnoreCase));
            if (tctl != null) return new SelectedSensor(tctl, $"{cpuHardware.Name} / {tctl.Name}");

            // 3. Exact normalized "CPU Package"
            var pkg = tempSensors.FirstOrDefault(s => s.Name.Equals("CPU Package", StringComparison.OrdinalIgnoreCase));
            if (pkg != null) return new SelectedSensor(pkg, $"{cpuHardware.Name} / {pkg.Name}");

            // 4. Exact normalized "Core Average"
            var avg = tempSensors.FirstOrDefault(s => s.Name.Equals("Core Average", StringComparison.OrdinalIgnoreCase));
            if (avg != null) return new SelectedSensor(avg, $"{cpuHardware.Name} / {avg.Name}");

            // No guessing
            return null;
        }

        public static SelectedSensor? SelectGpuSensor(IEnumerable<IHardware> hardwareList, string? preferredIdentifier = null)
        {
            var gpuHardware = hardwareList.FirstOrDefault(h =>
                h.HardwareType == HardwareType.GpuNvidia ||
                h.HardwareType == HardwareType.GpuAmd ||
                h.HardwareType == HardwareType.GpuIntel
            );
            if (gpuHardware == null) return null;

            var tempSensors = gpuHardware.Sensors
                .Where(s => s.SensorType == SensorType.Temperature)
                .ToList();

            if (tempSensors.Count == 0) return null;

            // 1. Preferred identifier
            if (!string.IsNullOrEmpty(preferredIdentifier))
            {
                var match = tempSensors.FirstOrDefault(s => s.Identifier.ToString().Equals(preferredIdentifier, StringComparison.OrdinalIgnoreCase));
                if (match != null) return new SelectedSensor(match, $"{gpuHardware.Name} / {match.Name}");
            }

            // 2. Exact normalized "GPU Core"
            var core = tempSensors.FirstOrDefault(s => s.Name.Equals("GPU Core", StringComparison.OrdinalIgnoreCase));
            if (core != null) return new SelectedSensor(core, $"{gpuHardware.Name} / {core.Name}");

            // 3. Exact normalized "GPU Package"
            var pkg = tempSensors.FirstOrDefault(s => s.Name.Equals("GPU Package", StringComparison.OrdinalIgnoreCase));
            if (pkg != null) return new SelectedSensor(pkg, $"{gpuHardware.Name} / {pkg.Name}");

            // 4. If exactly one sensor
            if (tempSensors.Count == 1)
            {
                var single = tempSensors[0];
                return new SelectedSensor(single, $"{gpuHardware.Name} / {single.Name}");
            }

            // No ambiguous guessing
            return null;
        }
    }
}