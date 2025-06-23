{ pkgs ? import <nixpkgs> {} }:

pkgs.mkShell {
  buildInputs = [
    pkgs.python3
    pkgs.gcc  # For libstdc++.so.6
  ];

  # Ensure libstdc++.so.6 is accessible
  LD_LIBRARY_PATH = "${pkgs.stdenv.cc.cc.lib}/lib";

  # Install Python packages into a virtual environment
  shellHook = ''
    # Create and activate a virtual environment
    python -m venv .venv
    source .venv/bin/activate

    # Upgrade pip and install packages
    pip install --upgrade pip
    pip install \
      "pip>=24.0,<25" \
      "attrs>=24.3.0,<25" \
      "idna>=3.10,<4" \
      "multidict>=6.1.0,<7" \
      "propcache>=0.2.1,<0.3" \
      "yarl>=1.18.3,<2" \
      "aiohttp>=3.11.11,<4" \
      "aiosignal>=1.3.2,<2" \
      "frozenlist>=1.5.0,<2" \
      "aiohappyeyeballs>=2.4.4,<3" \
      "discord.py>=2.4.0,<3" \
      "tomli_w>=1.1.0,<2" \
      "pillow" \
      "pandas" \
      "emoji"  \
      "requests"

    echo "Virtual environment ready. Run 'python main.py'."
  '';
}
