# contrib

Optional helpers that aren't part of the harness itself.

## `ollama.service`

A user-level systemd unit (`systemctl --user`) that keeps a locally-installed
Ollama daemon running without root — handy when you extracted Ollama into your
home directory instead of using the system-wide install. Install steps are in
the file's header comments. See the "Running Ollama (local & remote)" section of
the top-level [README](../README.md) for model sizing and remote-host tips.
