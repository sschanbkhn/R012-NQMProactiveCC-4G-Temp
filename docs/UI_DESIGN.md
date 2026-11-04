# UI_DESIGN.md — Thiết kế Giao diện UC01

> Module R012-NQMProactiveCC trong Automation_Noc1_FE
> 2 Tab chính: Tab1 (Tác động trạm) + Tab2 (Lịch sử CR)
> Tech: React 17, TypeScript, Ant Design 5, TanStack Query/Table,
>       Leaflet + react-leaflet, Recharts, react-hook-form + zod

---

## 1. ENTRY POINT & ROUTING

```typescript
// src/components/RNOC1/R012-NQMProactiveCC/R012HomeNQMProactiveCC.tsx
// Route: /r012-nqm-proactive-cc
// Đăng ký trong menu_config.json + MainPageRoute.tsx

import { Tabs } from 'antd'
import Tab1TacDongTram from './Tab1/Tab1TacDongTram'
import Tab2LichSuCR from './Tab2/Tab2LichSuCR'

export default function R012HomeNQMProactiveCC() {
  return (
    <Tabs defaultActiveKey="tab1" items={[
      { key: 'tab1', label: 'Tác động trạm', children: <Tab1TacDongTram /> },
      { key: 'tab2', label: 'Lịch sử CR',    children: <Tab2LichSuCR /> },
    ]} />
  )
}
```

---

## 2. FOLDER STRUCTURE — FE MODULE

```
src/components/RNOC1/R012-NQMProactiveCC/
├── R012HomeNQMProactiveCC.tsx     ← entry, Tab layout
├── types/
│   └── index.ts                   ← TS interfaces
├── services/
│   └── R012Service.ts             ← Axios calls
├── hooks/
│   ├── useCrSession.ts            ← TanStack Query
│   ├── useSseStream.ts            ← SSE consumer
│   ├── useStations.ts             ← danh sách trạm
│   └── useQosMetrics.ts           ← CTS QoS 48h (F33)
├── Tab1/
│   ├── Tab1TacDongTram.tsx        ← layout Tab1
│   ├── ZoneA/
│   │   ├── StationSearchGrid.tsx  ← TanStack Table
│   │   └── ConfirmTriggerModal.tsx
│   ├── ZoneB/
│   │   ├── NetworkMap.tsx         ← Leaflet map
│   │   └── SectorBeam.tsx         ← vẽ sector H1/H2/H3
│   ├── ZoneC/
│   │   ├── CrResultsByDirection.tsx ← kết quả theo hướng
│   │   └── SseProgressLog.tsx     ← 18 bước real-time
│   ├── WidgetF33/
│   │   └── QosSparkline.tsx       ← 48h hourly chart
│   └── ZoneE/
│       └── QoeQosCharts.tsx       ← 10 điểm before/after
└── Tab2/
    ├── Tab2LichSuCR.tsx           ← layout Tab2
    ├── StatsStrip.tsx             ← 4 số tổng hợp
    ├── SessionHistoryList.tsx     ← TanStack Table
    └── EvaluationDetail.tsx       ← chi tiết session
```

---

## 3. TYPESCRIPT INTERFACES

```typescript
// types/index.ts

export interface Tram {
  tram_id:      string
  tram_name:    string
  ten_quan_ly:  string | null
  ma_csht:      string | null
  longitude:    number | null
  latitude:     number | null
  trang_thai:   'active' | 'inactive' | 'relocating'
  cr_status:    CrStatus | null
  cr_session_id: number | null
}

export type CrStatus =
  'PENDING' | 'RUNNING' | 'DONE' | 'FAILED' |
  'EVALUATING' | 'EVALUATED' | 'EVAL_PENDING'

export interface CrSession {
  id:            number
  tram_id:       string
  tram_name:     string
  action:        'shutdown' | 'cancel' | 'relocate'
  status:        CrStatus
  qoe_result:    'PASS' | 'FAIL' | 'INSUFFICIENT_DATA' | null
  qos_result:    'PASS' | 'FAIL' | 'INSUFFICIENT_DATA' | null
  qoe_before:    number | null
  qoe_after:     number | null
  qos_before:    number | null
  qos_after:     number | null
  executed_at:   string | null   // UTC ISO string
  evaluated_at:  string | null
  created_at:    string
}

export interface CellParam {
  cell_name:          string
  huong_id:           string
  priority:           number
  action_type:        'rsboost' | 'qrxlevmin' | 'skip'
  rsboost_before_cr:  number | null
  rsboost_new:        number | null
  qrxlevmin_before_cr: number | null
  qrxlevmin_new:      number | null
}

export interface SseEvent {
  step:      number
  step_name: string
  pct:       number
  status:    'running' | 'success' | 'failed' | 'skipped'
  msg:       string
  done?:     boolean
  error?:    string
}

export interface QosDataPoint {
  time:  string   // UTC ISO
  qos:   number   // 1.0 - 5.0
}

export interface QoeDataPoint {
  snapshot_date: string  // YYYY-MM-DD
  qoe_score:     number
  period:        'before' | 'after'
}
```

---

## 4. SERVICES — AXIOS

```typescript
// services/R012Service.ts
import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL + '/api/v1',
  timeout: 30000,
})

export const R012Service = {
  // Stations
  getStations: (params: { q?: string; status?: string; page?: number; size?: number }) =>
    api.get('/stations', { params }),

  // Trigger CR
  triggerCr: (body: { tram_id?: string; tram_name?: string; action: string }) =>
    api.post('/cr/trigger', body),

  // Sessions
  getSessions: (params: { q?: string; status?: string; from?: string; to?: string }) =>
    api.get('/sessions', { params }),

  getSessionDetail: (id: number) =>
    api.get(`/sessions/${id}`),

  // QoS 48h (F33)
  getQosMetrics: (cell_name: string) =>
    api.get(`/qos/${cell_name}`),
}
```

---

## 5. HOOKS

```typescript
// hooks/useSseStream.ts
import { useEffect, useRef, useState } from 'react'
import { SseEvent } from '../types'

export function useSseStream(sessionId: number | null) {
  const [events, setEvents] = useState<SseEvent[]>([])
  const [done, setDone]     = useState(false)
  const esRef = useRef<EventSource | null>(null)

  useEffect(() => {
    if (!sessionId) return
    const es = new EventSource(
      `${import.meta.env.VITE_API_BASE_URL}/api/v1/cr/stream/${sessionId}`
    )
    esRef.current = es

    es.onmessage = (e) => {
      const event: SseEvent = JSON.parse(e.data)
      setEvents(prev => [...prev, event])
      if (event.done || event.status === 'failed') {
        setDone(true)
        es.close()
      }
    }
    es.onerror = () => { setDone(true); es.close() }

    return () => es.close()
  }, [sessionId])

  return { events, done }
}

// hooks/useStations.ts
import { useQuery } from '@tanstack/react-query'
import { R012Service } from '../services/R012Service'

export function useStations(params: object) {
  return useQuery({
    queryKey: ['r012-stations', params],
    queryFn: () => R012Service.getStations(params).then(r => r.data),
    staleTime: 5 * 60 * 1000,  // 5 phút
  })
}
```

---

## 6. TAB 1 — LAYOUT ASCII

```
┌─────────────────────────────────────────────────────────────────┐
│  Tab 1: Tác động trạm                                          │
├──────────────────────────────┬──────────────────────────────────┤
│  ZONE A — Tìm kiếm trạm     │  ZONE B — Bản đồ (Leaflet)      │
│  [Search input            ]  │                                  │
│  ┌──────────────────────┐   │  ● Marker trạm cha               │
│  │ STT│Tên trạm│Địa danh│   │  ○ Markers cell lân cận          │
│  │ 1  │4G-CBG..│Cầu Bươu│   │  ─ Sector beam H1/H2/H3         │
│  │ 2  │...     │...     │   │                                  │
│  │[Trigger CR]│[Xem KQ] │   │                                  │
│  └──────────────────────┘   │                                  │
├──────────────────────────────┴──────────────────────────────────┤
│  ZONE C — Kết quả CR (SSE real-time)                           │
│  Progress: ████████░░ 78%  Step 14: SSH Import...              │
│  ┌─────────┬───────────┬────────────┬────────────┬───────────┐ │
│  │ Cell    │ Hướng     │ Action     │ Before     │ After     │ │
│  │CBG001M11│ H1 (P1)   │ rsboost    │ 0dB        │ 3dB       │ │
│  │CBG001M12│ H1 (P2)   │ rsboost    │ -3dB       │ 0dB       │ │
│  │CBG001M13│ H1 (P3)   │ qrxlevmin  │ -128       │ -132      │ │
│  └─────────┴───────────┴────────────┴────────────┴───────────┘ │
├────────────────────────────────────┬────────────────────────────┤
│  WIDGET F33 — QoS Sparkline 48h   │  ZONE E — QoE/QoS Charts  │
│  cell1: ▁▂▃▄▃▂▁▂▃▄▅▄▃▂           │  (hiện sau khi EVALUATED)  │
│  cell2: ▂▃▄▅▄▃▂▁▂▃▄▃▂▁           │  QoE: ──●──●──●──●──       │
│  cell3: ▃▄▅▄▃▂▁▂▃▄▅▄▃▂           │  QoS: ──●──●──●──●──       │
└────────────────────────────────────┴────────────────────────────┘
```

---

## 7. ZONE A — StationSearchGrid

```typescript
// Tab1/ZoneA/StationSearchGrid.tsx
// TanStack Table v8, server-side pagination

Columns:
  STT          | số thứ tự (auto)
  tram_id      | ID Trạm
  tram_name    | Tên trạm
  ten_quan_ly  | Địa danh
  ma_csht      | Mã CSHT
  trang_thai   | Tag: active(xanh) / inactive(đỏ) / relocating(vàng)
  cr_status    | Tag: DONE(xanh) / RUNNING(xanh nhạt+spin) / FAILED(đỏ) / null(-)
  hanh_dong    | Button

Button logic:
  cr_status = null         → [Trigger CR]   (primary)
  cr_status = RUNNING      → [Đang chạy...] (loading, disabled)
  cr_status = DONE         → [Xem kết quả]  (default) + [Rollback] (danger)
  cr_status = FAILED       → [Retry]        (warning)
  cr_status = EVALUATED    → [Xem đánh giá] (default)

Search: debounce 300ms, tìm theo tram_id/tram_name/ten_quan_ly/ma_csht
Filter: dropdown trang_thai, dropdown cr_status
Pagination: server-side, page size 50
```

### Confirm Trigger Modal
```typescript
// Tab1/ZoneA/ConfirmTriggerModal.tsx
// Hiện trước khi trigger CR

Nội dung:
  "Xác nhận tác động trạm {tram_name}?"
  Hiện danh sách cell lân cận sẽ bị thay đổi (preview nếu có)
  Action dropdown: shutdown / cancel / relocate
  [Xác nhận] [Hủy]

Validation (react-hook-form + zod):
  action: required, enum['shutdown', 'cancel', 'relocate']
```

---

## 8. ZONE B — NetworkMap

```typescript
// Tab1/ZoneB/NetworkMap.tsx
// Leaflet + react-leaflet, OSM offline tiles zoom 6-12

Map layers:
  TileLayer:  offline tiles từ public/tiles/{z}/{x}/{y}.png
  Marker:     trạm cha (icon đặc biệt, màu đỏ/cam)
  CircleMarker: cell lân cận (màu theo hướng H1/H2/H3)
  Polyline:   sector beam từ trạm cha ra các cell

Center: tọa độ trạm cha khi select trong Zone A
Zoom:   12 (mặc định), min 6, max 16

// Tab1/ZoneB/SectorBeam.tsx
// Vẽ sector beam theo huong_id

Màu theo hướng:
  H1 (sector 1): xanh lam
  H2 (sector 2): xanh lá
  H3 (sector 3): cam

Hiển thị: polyline từ trạm cha → từng cell lân cận
           convex hull bao quanh các cell cùng hướng
```

---

## 9. ZONE C — CrResults + SSE Progress

```typescript
// Tab1/ZoneC/SseProgressLog.tsx
// SSE consumer, hiện 18 bước real-time

UI:
  Progress bar: Ant Design Progress (percent = pct từ SSE event)
  Log list: mỗi event = 1 dòng
    ✅ Step 3: Lấy được 9 cells, 3 hướng
    🔄 Step 14: SSH Import đang chạy...
    ❌ Step 14: SSH connection timeout

Màu:
  running: xanh nhạt + spin icon
  success: xanh đậm + check icon
  failed:  đỏ + x icon
  skipped: xám + skip icon

// Tab1/ZoneC/CrResultsByDirection.tsx
// Hiện sau khi SSE done=true

Table columns:
  Cell Name | Hướng | Priority | Action | Before | After | Trạng thái

Group by: huong_id (H1/H2/H3)
Màu hàng:
  rsboost:   nền xanh nhạt
  qrxlevmin: nền vàng nhạt
  skip:      nền xám nhạt, text mờ
```

---

## 10. WIDGET F33 — QosSparkline

```typescript
// Tab1/WidgetF33/QosSparkline.tsx
// 48h hourly QoS cho cells lân cận của trạm đang select

Data: GET /qos/{cell_name} → 48 điểm theo giờ
Chart: Recharts LineChart, mini size (height 60px)
       Mỗi cell 1 sparkline
       Không có axis labels (sparkline style)
       Tooltip khi hover: thời gian + QoS score

Trigger load: khi user select trạm trong Zone A
Stale time: 5 phút (TanStack Query)

Hiển thị: tối đa 6 cell (ưu tiên priority 1-2 trước)
```

---

## 11. ZONE E — QoeQosCharts

```typescript
// Tab1/ZoneE/QoeQosCharts.tsx
// Hiện inline trong Tab1 sau khi cr_session.status = EVALUATED
// Hoặc trong Tab2/EvaluationDetail.tsx (full page)

2 charts riêng biệt:

Chart 1 — QoE (nguồn: SOC):
  X-axis: 10 ngày (T-2, T-1, T+0, T+1→T+7)
  Y-axis: 0 - 5.0
  Line:   QoE score
  Điểm T+0 (CR day): màu amber/orange, tooltip "Ngày CR"
  Kết quả: badge PASS (xanh) / FAIL (đỏ) / INSUFFICIENT_DATA (xám)

Chart 2 — QoS (nguồn: CTS):
  Tương tự Chart 1 nhưng dùng qos_score

Component nhận props:
  sessionId: number
  → fetch từ GET /sessions/{id} → qoe_snapshots + qos_snapshots
  → filter 10 điểm hiển thị từ snapshot data
```

---

## 12. TAB 2 — LAYOUT ASCII

```
┌─────────────────────────────────────────────────────────────────┐
│  Tab 2: Lịch sử CR                                             │
├──────────────────────────────────────────────────────────────────┤
│  STATS STRIP                                                    │
│  [Tổng: 156]  [Hoàn thành: 120]  [Chờ đánh giá: 20]  [Lỗi: 16]│
├──────────────────────────────────────────────────────────────────┤
│  ZONE D — Lịch sử sessions                                     │
│  [Search...] [Filter status ▼] [Từ ngày] [Đến ngày]           │
│  ┌────┬──────────┬────────────┬──────────┬─────────┬─────────┐ │
│  │ ID │ Trạm    │ Ngày chạy  │ Status   │ QoE     │ QoS     │ │
│  │ 42 │CBG001M  │08/07/2026  │EVALUATED │✅ PASS  │❌ FAIL  │ │
│  │ 41 │HKM053   │07/07/2026  │DONE      │-        │-        │ │
│  │ 40 │...      │...         │FAILED    │-        │-        │ │
│  └────┴──────────┴────────────┴──────────┴─────────┴─────────┘ │
│                                                [Xem chi tiết →] │
└──────────────────────────────────────────────────────────────────┘
```

---

## 13. STATS STRIP

```typescript
// Tab2/StatsStrip.tsx
// 4 số tổng hợp, fetch từ GET /sessions với aggregate

4 cards:
  Tổng CR:       tổng số sessions
  Hoàn thành:    status IN (DONE, EVALUATED, EVAL_PENDING)
  Chờ đánh giá:  status = EVAL_PENDING
  Thất bại:      status = FAILED

Ant Design: Row + Col + Statistic component
Refresh: mỗi 5 phút hoặc khi trigger CR xong
```

---

## 14. SESSION HISTORY LIST

```typescript
// Tab2/SessionHistoryList.tsx
// TanStack Table v8, server-side pagination

Columns:
  ID           | session id, click → route /history/:id
  Trạm         | tram_name
  Action       | Tag: shutdown(xanh)/cancel(vàng)/relocate(cam)
  Ngày chạy    | executed_at (format GMT+7)
  Trạng thái   | Tag theo CrStatus
  QoE          | badge PASS/FAIL/- 
  QoS          | badge PASS/FAIL/-
  Chi tiết     | Button [Xem →]

Sort: created_at DESC (mặc định)
Filter: status dropdown, date range picker
Search: tram_id / tram_name

Click row / [Xem →]: navigate to /r012-nqm-proactive-cc/history/:id
```

---

## 15. EVALUATION DETAIL PAGE

```typescript
// pages/SessionDetailPage.tsx
// Route: /r012-nqm-proactive-cc/history/:session_id

Layout:
  Header: Thông tin session (tram_name, action, executed_at, status)
  
  Section 1 — Cell params table:
    cell_name | huong | priority | action | before | after
  
  Section 2 — CR Log (18 bước):
    collapsible list, icon theo status
  
  Section 3 — QoE/QoS Charts:
    reuse <QoeQosCharts sessionId={id} />
    Chỉ hiện nếu status = EVALUATED / EVAL_PENDING
    EVAL_PENDING: banner "Chờ đủ dữ liệu đánh giá"
  
  Section 4 — Alert (nếu có):
    banner đỏ nếu QoE hoặc QoS = FAIL
    "QoS degraded: 3.5 → 3.2 (-0.3)"

Button footer:
  [Rollback CR] (danger) — chỉ hiện nếu status = DONE/EVALUATED
  [Quay lại]
```

---

## 16. STATE MANAGEMENT

```
TanStack Query (server state):
  - useStations()        → cache 5 phút
  - useSessions()        → cache 1 phút
  - useSessionDetail()   → cache 5 phút
  - useQosMetrics()      → cache 5 phút

Local React State (UI state):
  - selectedTramId       → trạm đang select trong Zone A
  - activeSessionId      → session đang stream SSE
  - sseEvents            → array events từ SSE hook
  - mapCenter            → tọa độ bản đồ

KHÔNG dùng Redux/Zustand cho UC01:
  → TanStack Query + useState là đủ
  → Giữ đơn giản, không over-engineer
```

---

## 17. DATETIME DISPLAY

```typescript
// Tất cả datetime từ BE là UTC ISO string
// Convert sang GMT+7 trước khi hiển thị

import dayjs from 'dayjs'
import utc from 'dayjs/plugin/utc'
import timezone from 'dayjs/plugin/timezone'
dayjs.extend(utc)
dayjs.extend(timezone)

const VN_TZ = 'Asia/Ho_Chi_Minh'

export const formatDateTime = (utcStr: string) =>
  dayjs.utc(utcStr).tz(VN_TZ).format('DD/MM/YYYY HH:mm:ss')

export const formatDate = (utcStr: string) =>
  dayjs.utc(utcStr).tz(VN_TZ).format('DD/MM/YYYY')
```

---

## 18. CÁC LƯU Ý QUAN TRỌNG KHI CODE FE

```
1. KHÔNG sửa code UC khác đã có trong Automation_Noc1_FE
2. KHÔNG thay đổi routing, config chung của project
3. Chỉ thêm entry mới vào menu_config.json + MainPageRoute.tsx
4. Map tiles: dùng offline tiles (public/tiles/) — không dùng online CDN
5. Axios baseURL: lấy từ import.meta.env.VITE_API_BASE_URL — không hardcode
6. SSE: đóng EventSource khi component unmount (cleanup trong useEffect)
7. TanStack Table: dùng v8 API (khác v7 rất nhiều)
8. Ant Design 5: dùng component mới (Form.Item, Table columns với render)
9. Leaflet: import CSS trong component hoặc global
   import 'leaflet/dist/leaflet.css'
10. react-leaflet: fix icon default marker (vấn đề phổ biến với webpack)
    import L from 'leaflet'
    delete (L.Icon.Default.prototype as any)._getIconUrl
    L.Icon.Default.mergeOptions({ iconRetinaUrl: ..., iconUrl: ..., shadowUrl: ... })
```


## 20. BỔ SUNG UI RULES

### 20.1 cr_status = ROLLBACK_DONE
Thêm vào type CrStatus (types/index.ts):
| 'ROLLBACK_DONE'
Màu hiển thị:
ROLLBACK_DONE → #722ed1 (tím — phân biệt với DONE xanh lá)
Tag label: "Đã rollback"
Button logic Zone A (bổ sung):
cr_status = ROLLBACK_DONE → [Xem kết quả] (default)
KHÔNG hiện [Rollback] nữa
(đã về cấu hình gốc rồi)
Zone D Tab2: thêm filter option "Đã rollback" (ROLLBACK_DONE)

### 20.2 Empty State
Zone B (Map) — chưa chọn trạm:
→ Hiển thị bản đồ Việt Nam, zoom=6, center=[16.0, 106.0]
→ Không có marker
Zone C (SSE) — chưa chọn trạm:
<Empty description="Vui lòng chọn một trạm từ danh sách
                   để xem chi tiết và tiến hành tác động" />
Widget F33 — chưa chọn trạm:
<Empty description="Chọn trạm để xem QoS 48h" image={Empty.PRESENTED_IMAGE_SIMPLE} />
Zone E (Charts) — session chưa EVALUATED:
status = DONE/RUNNING    → <Empty description="Chờ đủ 21 ngày để đánh giá" />
status = EVAL_PENDING    → banner warning "Chưa đủ dữ liệu, hệ thống sẽ tự đánh giá lại"
status = EVALUATED       → hiện charts bình thường

### 20.3 Nút [Dừng theo dõi] — Zone C
Hiển thị: khi SSE đang streaming (done=false)
Vị trí:   góc phải progress bar
Label:    [Dừng theo dõi]
Style:    Ant Design Button type="default" danger
Hành động:
→ đóng EventSource (es.close())
→ KHÔNG gửi request nào lên BE
→ KHÔNG dừng CR đang chạy ở backend
→ Hiện banner: "Đã ngắt theo dõi. CR vẫn đang chạy ở hệ thống.
Vào Tab 2 để xem kết quả sau."
Note trong code (useSseStream.ts):
const stopWatching = () => {
esRef.current?.close()
setDone(true)
setManualStop(true)  // để hiện banner thông báo
}

### 20.4 Recharts — Tooltip & Y-axis
Zone E Charts (QoE + QoS):
Y-axis domain: ['dataMin - 0.5', 'dataMax + 0.5']
→ KHÔNG cố định 0-5 (đường sẽ phẳng, khó thấy trend)
→ auto scale theo data thực tế
Tooltip format:
QoE chart: "{value} điểm QoE"
QoS chart: "{value} điểm QoS"
CR day (T+0): "Ngày CR: {date}"
Widget F33 Sparkline:
Y-axis: ẩn (sparkline style)
Tooltip: "{time GMT+7}: {qos} điểm"
domain: ['dataMin - 0.2', 'dataMax + 0.2']


## 19. MÀU SẮC & DESIGN TOKENS

### Màu trạng thái
cr_status / trang_thai:
active / DONE / PASS      → #52c41a (xanh lá — Ant Design success)
RUNNING / EVALUATING      → #1677ff (xanh dương — Ant Design processing)
FAILED                    → #ff4d4f (đỏ — Ant Design error)
EVAL_PENDING / relocating → #faad14 (vàng — Ant Design warning)
inactive / skip           → #d9d9d9 (xám — Ant Design default)
INSUFFICIENT_DATA         → #8c8c8c (xám đậm)
action type (cell):
rsboost                   → nền #e6f4ff (xanh nhạt)
qrxlevmin                 → nền #fffbe6 (vàng nhạt)
skip                      → nền #f5f5f5 (xám nhạt), text #bfbfbf
sector beam / map marker:
H1 (sector 1)             → #1677ff (xanh dương)
H2 (sector 2)             → #52c41a (xanh lá)
H3 (sector 3)             → #fa8c16 (cam)
Trạm cha (marker)         → #ff4d4f (đỏ, icon lớn hơn)
Cell lân cận (marker)     → màu theo hướng H1/H2/H3, icon nhỏ hơn

### Chart colors
QoE line (SOC):             → #1677ff (xanh dương)
QoS line (CTS):             → #52c41a (xanh lá)
CR day (T+0) marker:        → #faad14 (amber/orange)
Before zone (T-7→T-1):      → nền #fff7e6 (vàng cực nhạt)
After zone (T+1→T+7):       → nền #f6ffed (xanh cực nhạt)

### Progress bar
0-50%:    #1677ff (xanh)
51-99%:   #1677ff (xanh)
100%:     #52c41a (xanh lá — hoàn thành)
Failed:   #ff4d4f (đỏ)

### Kích thước component
Zone A (grid):        height 300px, scroll nếu nhiều row
Zone B (map):         height 400px, width 100%
Zone C (SSE log):     height 250px, overflow-y scroll
Widget F33 (sparkline): height 60px mỗi cell, max 6 cells
Zone E (charts):      height 250px mỗi chart
Stats Strip:          height 80px, 4 cards ngang
Tab2 History List:    height calc(100vh - 200px)

### Font & spacing (Ant Design defaults)
Font:        -apple-system, Roboto, sans-serif (Ant Design default)
Font size:   14px (body), 12px (table cell), 16px (card title)
Border radius: 6px (card, modal), 4px (tag, badge)
Spacing:     Ant Design Space component, gap 8px/16px/24px



