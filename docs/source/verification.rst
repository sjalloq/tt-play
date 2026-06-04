Verification
============

Two checks: ``tt-smi`` for the host-side view, and a TT-NN smoke test for the
full host→device→host path.

tt-smi
------

With the venv active (``source sourceme``), ``tt-smi`` reads telemetry from the
card. The ``-s`` flag dumps a machine-readable snapshot:

.. code-block:: console

   $ tt-smi -s

The snapshot reports the host environment, software versions, and a
``device_info`` block with live telemetry (clocks, temperatures, board ID,
firmware bundle), one entry per card. See :doc:`reference/current-state` for
the snapshot from this machine.

No devices reported indicates: the driver is not loaded
(``lsmod | grep tenstorrent``), the BIOS AER setting is wrong (see
:doc:`hardware`), or the card needs a cold power-cycle.

TT-NN smoke test
----------------

``demos/smoke_add.py`` is a torch-free TT-NN test. It:

#. opens device 0,
#. creates two 32×32 ``bfloat16`` tensors on the device (3.0 and 4.0),
#. runs an elementwise ``add`` on the Tensix cores,
#. reads the result back and checks every element is ≈ 7.0 (within bf16
   rounding).

Exit code 0 / ``RESULT: PASS`` confirms the full path: driver, hugepages,
runtime, and Tensix cores. It runs inside the Metalium container, which ships
``ttnn`` + ``numpy`` but not torch:

.. code-block:: console

   $ ./util/tt-metalium -c "python3 demos/smoke_add.py"
   2026-06-04 21:41:48.935 | DEBUG    | ttnn:<module>:79 - Initial ttnn.CONFIG:
   Config{cache_path=/root/.cache/ttnn,model_cache_path=/root/.cache/ttnn/models,tmp_dir=/tmp/ttnn,enable_model_cache=false,enable_fast_runtime_mode=true,throw_exception_on_fallback=false,enable_logging=false,enable_graph_report=false,enable_graph_python_stack_traces=false,enable_detailed_buffer_report=false,enable_detailed_tensor_report=false,enable_comparison_mode=false,comparison_mode_should_raise_exception=false,comparison_mode_pcc=0.9999,root_report_path=generated/ttnn/reports,report_name=std::nullopt,std::nullopt}
   2026-06-04 21:41:49.355 | info     |          Device | Opening user mode device driver (tt_cluster.cpp:228)
   2026-06-04 21:41:49.355 | info     |             UMD | Cluster constructor started. (cluster.cpp:332)
   2026-06-04 21:41:49.355 | info     |             UMD | Creating TopologyDiscovery for architecture: blackhole (topology_discovery.cpp:74)
   2026-06-04 21:41:49.355 | info     |             UMD | Starting topology discovery. (topology_discovery.cpp:91)
   2026-06-04 21:41:49.356 | warning  |             UMD | TENSTORRENT_IOCTL_SET_POWER_STATE failed on device 0: Invalid argument (pci_device.cpp:1090)
   2026-06-04 21:41:49.357 | info     |             UMD | Established firmware bundle version: 18.10.0 (topology_discovery.cpp:548)
   2026-06-04 21:41:49.357 | info     |             UMD | Completed topology discovery. (topology_discovery.cpp:95)
   2026-06-04 21:41:49.414 | warning  |             UMD | TENSTORRENT_IOCTL_SET_POWER_STATE failed on device 0: Invalid argument (pci_device.cpp:1090)
   2026-06-04 21:41:49.415 | info     |             UMD | Opening local chip ids/PCIe ids: {0}/[0] and remote chip ids {} (cluster.cpp:169)
   2026-06-04 21:41:49.415 | info     |             UMD | IOMMU: enabled (cluster.cpp:143)
   2026-06-04 21:41:49.415 | info     |             UMD | KMD version: 2.8.0 (cluster.cpp:146)
   2026-06-04 21:41:49.415 | info     |             UMD | Cluster constructor completed. (cluster.cpp:504)
   2026-06-04 21:41:49.416 | info     |             UMD | Starting devices in cluster (cluster.cpp:1258)
   2026-06-04 21:41:49.482 | info     |             UMD | Starting devices in cluster completed. (cluster.cpp:1266)
   2026-06-04 21:41:49.647 | info     |     Distributed | Using auto discovery to generate mesh graph. (metal_env.cpp:362)
   2026-06-04 21:41:49.647 | info     |     Distributed | Constructing control plane using auto-discovery (no mesh graph descriptor). (metal_env.cpp:424)
   2026-06-04 21:41:49.647 | info     |             UMD | Creating TopologyDiscovery for architecture: blackhole (topology_discovery.cpp:74)
   2026-06-04 21:41:49.647 | info     |             UMD | Starting topology discovery. (topology_discovery.cpp:91)
   2026-06-04 21:41:49.648 | warning  |             UMD | TENSTORRENT_IOCTL_SET_POWER_STATE failed on device 0: Invalid argument (pci_device.cpp:1090)
   2026-06-04 21:41:49.649 | info     |             UMD | Established firmware bundle version: 18.10.0 (topology_discovery.cpp:548)
   2026-06-04 21:41:49.649 | info     |             UMD | Completed topology discovery. (topology_discovery.cpp:95)
   2026-06-04 21:41:49.650 | warning  |          Always | Unknown motherboard 'X570 AORUS MASTER' for chip_id=0 (bus_id=0xb) — defaulting tray_id to 0. Add this motherboard and its bus IDs to mobo_to_bus_ids in physical_system_discovery.cpp. (physical_system_discovery.cpp:68)
   2026-06-04 21:41:49.655 | info     |    BuildKernels | Using pre-compiled firmware from: /opt/venv/lib/python3.10/site-packages/ttnn/tt_metal/pre-compiled/4540669710501409641/ (build_env_manager.cpp:320)
   2026-06-04 21:41:51.822 | info     |           Metal | ShmResourceTracker: removed orphaned shm '/tt_device_7770692653949780243_memory' (shm_resource_tracker.cpp:282)
   2026-06-04 21:41:52.988 | info     |           Metal | [Real-time profiler] Device 0 sync complete: 100 samples, frequency=1.349990 GHz, device_time_at_sync=7105187658477 cycles (realtime_profiler_manager.cpp:1126)
   (numpy extraction unavailable: setting an array element with a sequence.; printing tensor repr instead)
   ttnn.Tensor([[ 7.0000,  7.0000,  ...,  7.0000,  7.0000],
               [ 7.0000,  7.0000,  ...,  7.0000,  7.0000],
               ...,
               [ 7.0000,  7.0000,  ...,  7.0000,  7.0000],
               [ 7.0000,  7.0000,  ...,  7.0000,  7.0000]], shape=Shape([32, 32]), dtype=DataType::BFLOAT16, layout=Layout::ROW_MAJOR)
   RESULT: PASS
   2026-06-04 21:41:53.552 | info     |    BuildKernels | JIT cache stats: 0/13 hits (0.0%) [0 cached, 0 build-once dedup, 0 merged artifacts, 0 merged genfiles] (build_cache_telemetry.cpp:207)
   2026-06-04 21:41:53.552 | info     |    BuildKernels | JIT telemetry: 2 registered TelemetryTokens (build_cache_telemetry.cpp:230)
   2026-06-04 21:41:53.554 | info     |          Device | Closing user mode device drivers (tt_cluster.cpp:512)
   2026-06-04 21:41:53.554 | info     |             UMD | Closing devices in cluster (cluster.cpp:1271)
   2026-06-04 21:41:54.010 | info     |             UMD | Closing devices in cluster completed. (cluster.cpp:1280)
   2026-06-04 21:41:54.010 | info     |             UMD | Cluster destructor started. (cluster.cpp:712)
   2026-06-04 21:41:54.010 | info     |             UMD | Cluster destructor completed. (cluster.cpp:715)
   2026-06-04 21:41:54.011 | warning  |             UMD | TENSTORRENT_IOCTL_SET_POWER_STATE failed on device 0: Invalid argument (pci_device.cpp:1090)
