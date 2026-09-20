using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Threading;
using LibreHardwareMonitor.Hardware;

namespace OpenRGBTempSync.SensorBridge
{
    public class Program
    {
        public const string Version = "1.0.0";
        public const string LibraryVersion = "0.9.6";

        public static int Main(string[] args)
        {
            int intervalMs = 1000;
            string? preferredCpu = null;
            string? preferredGpu = null;

            for (int i = 0; i < args.Length; i++)
            {
                if (args[i] == "--interval" && i + 1 < args.Length && int.TryParse(args[i + 1], out int parsedInterval))
                {
                    intervalMs = Math.Max(200, Math.Min(10000, parsedInterval));
                    i++;
                }
                else if (args[i] == "--preferred-cpu" && i + 1 < args.Length)
                {
                    preferredCpu = args[++i];
                }
                else if (args[i] == "--preferred-gpu" && i + 1 < args.Length)
                {
                    preferredGpu = args[++i];
                }
            }

            // Output hello record immediately
            int currentPid = Process.GetCurrentProcess().Id;
            Console.Out.WriteLine(SensorProtocol.SerializeHello(Version, LibraryVersion, currentPid, intervalMs));
            Console.Out.Flush();

            Computer? computer = null;
            try
            {
                computer = new Computer
                {
                    IsCpuEnabled = true,
                    IsGpuEnabled = true
                };
                computer.Open();
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine($"[ERROR] Failed to open hardware monitor: {ex.Message}");
                Console.Out.WriteLine(SensorProtocol.SerializeFatal(20, $"Hardware init failed: {ex.Message}"));
                Console.Out.Flush();
                return 20;
            }

            var cts = new CancellationTokenSource();
            Console.CancelKeyPress += (s, e) =>
            {
                e.Cancel = true;
                cts.Cancel();
            };

            // Monitor stdin in background: if stdin closes (parent process terminated), shut down
            var stdinMonitor = new Thread(() =>
            {
                try
                {
                    while (Console.In.ReadLine() != null) { }
                }
                catch { }
                finally
                {
                    cts.Cancel();
                }
            })
            { IsBackground = true };
            stdinMonitor.Start();

            long sequence = 0;

            try
            {
                while (!cts.Token.IsCancellationRequested)
                {
                    sequence++;
                    var warnings = new List<string>();

                    foreach (var hw in computer.Hardware)
                    {
                        hw.Update();
                    }

                    var selectedCpu = SensorSelector.SelectCpuSensor(computer.Hardware, preferredCpu);
                    var selectedGpu = SensorSelector.SelectGpuSensor(computer.Hardware, preferredGpu);

                    float? cpuTemp = null;
                    string cpuSource = "None";
                    if (selectedCpu?.Sensor != null)
                    {
                        cpuTemp = selectedCpu.Sensor.Value;
                        cpuSource = selectedCpu.SourceName;
                    }
                    else
                    {
                        warnings.Add("No matching CPU temperature sensor found.");
                    }

                    float? gpuTemp = null;
                    string gpuSource = "None";
                    if (selectedGpu?.Sensor != null)
                    {
                        gpuTemp = selectedGpu.Sensor.Value;
                        gpuSource = selectedGpu.SourceName;
                    }
                    else
                    {
                        warnings.Add("No matching GPU temperature sensor found.");
                    }

                    string sampleJson = SensorProtocol.SerializeSample(sequence, cpuTemp, gpuTemp, cpuSource, gpuSource, warnings);
                    Console.Out.WriteLine(sampleJson);
                    Console.Out.Flush();

                    if (cts.Token.WaitHandle.WaitOne(intervalMs))
                    {
                        break;
                    }
                }
            }
            catch (Exception ex)
            {
                Console.Error.WriteLine($"[FATAL] Runtime error in sensor loop: {ex.Message}");
                Console.Out.WriteLine(SensorProtocol.SerializeFatal(40, ex.Message));
                Console.Out.Flush();
                return 40;
            }
            finally
            {
                try
                {
                    computer.Close();
                }
                catch { }
            }

            return 0;
        }
    }
}