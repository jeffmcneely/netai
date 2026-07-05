# NetAI

A web front end for [pybatfish](https://github.com/batfish/pybatfish) with some AI hooks for ACL work. You upload network configs to S3, point it at a Batfish server, and get a browser-based interface for analysis and ACL optimization.

## What it does

**Config analysis** (`/analyze`)  
Upload Cisco/NX-OS/ASA configs, run Batfish analysis, and browse results:

- Unreachable ACL rules
- Defined/undefined/unused structures
- Interface inventory
- VLAN table
- SNMP community check
- Explorer (raw Batfish query results)

**ACL optimization** (`/acl-optimize`)  
Paste an ACL, run it through an LLM (OpenAI or Claude), and get back:

- Optimized ACL text
- Verification against original (Batfish-backed)
- CLI commands to deploy the changes
- "Remove junk" — async job that strips redundant/shadowed entries

**Search**  
Search configs for IP addresses or string patterns across all uploaded files.
