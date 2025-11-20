-- Force analog profile for card 2 (Realtek ALC897)
rule = {
  matches = {
    {
      { "device.name", "equals", "alsa_card.pci-0000_09_00.4" },
    },
  },
  apply_properties = {
    ["api.acp.auto-profile"] = true,
    ["api.acp.auto-port"] = true,
  },
}

table.insert(alsa_monitor.rules, rule)
