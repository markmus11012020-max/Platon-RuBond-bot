"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";

import { moneyCompact, num, pct } from "@/lib/format";
import type { AllocationSlice, PositionCard } from "@/lib/types";

export function AllocationChart({ data }: { data: AllocationSlice[] }) {
  return (
    <>
      <div className="chart-wrap" style={{ height: 190 }}>
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={data}
              dataKey="value_rub"
              nameKey="name"
              cx="50%"
              cy="50%"
              innerRadius={58}
              outerRadius={82}
              paddingAngle={3}
              stroke="rgba(7,17,15,0.9)"
              strokeWidth={2}
              isAnimationActive={false}
            >
              {data.map((item) => (
                <Cell key={item.name} fill={item.color} />
              ))}
            </Pie>
            <Tooltip
              contentStyle={{
                background: "#0a1814",
                border: "1px solid rgba(167,243,208,0.2)",
                borderRadius: 12,
                fontSize: 11,
                color: "#ecfdf5",
              }}
              formatter={(value, name) => [
                moneyCompact(Number(value)),
                String(name),
              ]}
            />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <div className="chart-legend">
        {data.map((item) => (
          <div className="legend-item" key={item.name}>
            <span
              className="legend-dot"
              style={{ background: item.color }}
            />
            <span className="legend-name">{item.name}</span>
            <span style={{ marginLeft: "auto", color: "var(--muted-2)" }}>
              {pct(item.share_pct, 0)}
            </span>
          </div>
        ))}
      </div>
    </>
  );
}

export function YieldDurationChart({ positions }: { positions: PositionCard[] }) {
  const data = positions
    .filter((item) => item.duration_years !== null && item.ytm_pct !== null)
    .map((item) => ({
      name: item.name,
      duration: item.duration_years,
      ytm: item.ytm_pct,
      value: item.value_rub,
      rating: item.rating,
      fill:
        item.rating === "AAA" || item.rating === "AA-"
          ? "#7dd3fc"
          : item.rating?.startsWith("A")
            ? "#38d9a9"
            : "#f6c453",
    }));

  return (
    <div className="chart-wrap" style={{ height: 220 }}>
      <ResponsiveContainer width="100%" height="100%">
        <ScatterChart margin={{ top: 8, right: 8, bottom: 8, left: 0 }}>
          <CartesianGrid stroke="rgba(167,243,208,0.08)" strokeDasharray="3 3" />
          <XAxis
            type="number"
            dataKey="duration"
            name="Дюрация"
            unit=" г."
            tick={{ fill: "#6f9187", fontSize: 10 }}
            axisLine={{ stroke: "rgba(167,243,208,0.12)" }}
            tickLine={false}
            domain={[0, 2.2]}
          />
          <YAxis
            type="number"
            dataKey="ytm"
            name="YTM"
            unit="%"
            tick={{ fill: "#6f9187", fontSize: 10 }}
            axisLine={{ stroke: "rgba(167,243,208,0.12)" }}
            tickLine={false}
            domain={[15, 28]}
          />
          <ZAxis type="number" dataKey="value" range={[80, 420]} />
          <Tooltip
            cursor={{ strokeDasharray: "3 3" }}
            content={({ active, payload }) => {
              if (!active || !payload?.length) return null;
              const item = payload[0]?.payload as (typeof data)[number];
              return (
                <div
                  style={{
                    background: "#0a1814",
                    border: "1px solid rgba(167,243,208,0.2)",
                    borderRadius: 12,
                    padding: "8px 10px",
                    fontSize: 11,
                    color: "#ecfdf5",
                  }}
                >
                  <div style={{ fontWeight: 700 }}>{item.name}</div>
                  <div style={{ color: "#8aa9a0", marginTop: 3 }}>
                    YTM {pct(item.ytm)} · дюр. {num(item.duration)} г.
                  </div>
                  <div style={{ color: "#8aa9a0" }}>
                    {moneyCompact(item.value)} · {item.rating}
                  </div>
                </div>
              );
            }}
          />
          <Scatter data={data} isAnimationActive={false}>
            {data.map((item) => (
              <Cell key={item.name} fill={item.fill} />
            ))}
          </Scatter>
        </ScatterChart>
      </ResponsiveContainer>
    </div>
  );
}

export function RatingBars({ mix }: { mix: Record<string, number> }) {
  const data = Object.entries(mix).map(([rating, value]) => ({
    rating,
    value,
    fill:
      rating === "AAA" || rating === "AA-"
        ? "#7dd3fc"
        : rating.startsWith("A")
          ? "#38d9a9"
          : "#f6c453",
  }));
  return (
    <div className="chart-wrap" style={{ height: 170 }}>
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -22 }}>
          <CartesianGrid stroke="rgba(167,243,208,0.08)" strokeDasharray="3 3" />
          <XAxis
            dataKey="rating"
            tick={{ fill: "#6f9187", fontSize: 10 }}
            axisLine={{ stroke: "rgba(167,243,208,0.12)" }}
            tickLine={false}
          />
          <YAxis
            unit="%"
            tick={{ fill: "#6f9187", fontSize: 10 }}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            cursor={{ fill: "rgba(56,217,169,0.06)" }}
            contentStyle={{
              background: "#0a1814",
              border: "1px solid rgba(167,243,208,0.2)",
              borderRadius: 12,
              fontSize: 11,
              color: "#ecfdf5",
            }}
            formatter={(value) => [pct(Number(value), 1), "Доля"]}
          />
          <Bar dataKey="value" radius={[6, 6, 0, 0]} isAnimationActive={false}>
            {data.map((item) => (
              <Cell key={item.rating} fill={item.fill} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
