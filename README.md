
https://yolaaandaw-dotcom.github.io/sushiro-index/


# 朗区房査定 · Sushiro Proximity Index

自包含的单文件查询器：输入地址 → 最近的寿司朗距离 + 朗区房等级。数据从 OpenStreetMap 拉取后烘进 HTML，无需后端。

---

## 文件说明

- `build.py` — 抓 Overpass 数据、写入 `index.html`。**只在数据需要更新时跑。**
- `template.html` — HTML 模板，里面有 `/*__SUSHIRO_DATA__*/[]` 占位符。
- `index.html` — `build.py` 生成的产物，**这是要 deploy 的文件**。

---

## 部署步骤

### 1. 本地生成 `index.html`

把 `build.py` 和 `template.html` 放在同一个文件夹，然后：

```bash
python3 build.py
```

应该会看到类似输出：

```
→ Trying https://overpass-api.de/api/interpreter
  ✓ Got 823 raw elements
✓ After dedupe: 821 locations
  Distribution: {'JP': 680, 'TW': 58, 'HK': 36, 'SG': 13, ...}
✓ Wrote index.html (142.3 KB, 821 stores embedded)
```

> Overpass 公用节点偶尔抽风，脚本会自动 try 四个备用节点。如果全挂了，等两分钟再跑。

### 2. 推到 GitHub Pages

**方案 A：用户站（推荐，URL 最短）**

```bash
# 仓库名必须是 <your-username>.github.io
gh repo create <username>.github.io --public
cd <username>.github.io
cp /path/to/index.html .
git add index.html
git commit -m "initial"
git push
```

访问：`https://<username>.github.io/` — 几分钟后生效。

**方案 B：项目站**

```bash
gh repo create sushiro-index --public
cd sushiro-index
cp /path/to/index.html .
git add index.html
git commit -m "initial"
git push
```

然后去仓库 Settings → Pages → Source 选 `main` 分支 / `/ (root)`，Save。

访问：`https://<username>.github.io/sushiro-index/`

### 3. 更新数据

OSM 数据每几个月可能有新店加进来，想更新就：

```bash
python3 build.py
git add index.html
git commit -m "refresh data"
git push
```

---

## 技术要点

- **数据源**：OpenStreetMap Overpass API，按 `brand=スシロー` 等多语言 tag 过滤
- **数据体积**：~140KB（压缩后 ~40KB），加载没压力
- **地理编码**：Nominatim → Photon 自动降级，都是 HTTPS 公开服务
- **定位**：浏览器 Geolocation API → IP 定位（ipapi.co / ipwho.is / geojs）自动降级
- **距离算法**：Haversine，直线距离。不考虑山、海、签证

GitHub Pages 走 HTTPS，所以浏览器定位会正常弹权限框——Claude 预览里不工作就是因为 iframe 沙盒拦了这个，deploy 之后就没问题了。

---

## 可能踩的坑

**Q: 运行 `build.py` 报 `All Overpass endpoints failed`**
A: Overpass 公共节点在高峰期会 503 / 429。等 2-5 分钟再试。或者凌晨跑。

**Q: 跑出来很少？**
A: 检查 stderr 里的 `Distribution:`。正常应该有 ~680 JP + ~60 TW + ~40 HK 这种量级。太少说明 OSM 返回不全，重跑。

**Q: Nominatim 在 github.io 偶尔失败**
A: 它有 QPS 限制（~1/秒 per IP）。脚本已经做了 Photon 降级，基本不会两个都挂。
