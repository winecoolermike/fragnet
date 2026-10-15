# DNS rollback snapshot (before Cloudflare Pages cutover)
Zone: esportsscoreboard.com (f9054803a855286f380c6c2dd4644d3b)
Captured: 2026-10-15 ~16:25 PT

Root A (DNS-only, not proxied):
- 185.199.111.153  id=b3a4dbfb9b2a064478d2ca6c8fb3fc91
- 185.199.110.153  id=9d6a0d9f1ab10f3c105026a1a9a30416
- 185.199.109.153  id=5032a59b3ca20bc472cf84f76f62358f
- 185.199.108.153  id=90eaa7dfbac68268c54ff24ebcbc010c

www CNAME (DNS-only):
- winecoolermike.github.io  id=09dcea4d43182704d263eb2d829592c4

To roll back: delete the Pages CNAMEs, recreate these five records, and re-enable GitHub Pages.
