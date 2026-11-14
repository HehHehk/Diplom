import { useQuery } from "@tanstack/react-query";
import { Alert, Empty, Skeleton, Typography } from "antd";
import { api } from "../api/client";
import type { RecommendationList } from "../api/types";
import EquipmentCard from "./EquipmentCard";

export default function EquipmentRail({
  title,
  source,
  layout = "grid",
}: {
  title: string;
  source: { kind: "recommendations"; equipmentId: number } | { kind: "popular" };
  layout?: "grid" | "row";
}) {
  const path =
    source.kind === "popular"
      ? "/equipment/popular?limit=8"
      : `/equipment/${source.equipmentId}/recommendations?limit=8`;

  const { data, isLoading } = useQuery({
    queryKey: ["rail", source],
    queryFn: async () => (await api.get<RecommendationList>(path)).data,
  });

  if (isLoading) return <Skeleton active paragraph={{ rows: 2 }} />;
  if (!data || data.items.length === 0) {
    return <Empty description="Пока нет данных" />;
  }

  return (
    <div className="rail">
      <div className="rail-head">
        <Typography.Title level={4}>{title}</Typography.Title>
        {data.strategy === "popular" ? (
          <Alert type="info" showIcon title="Показаны популярные позиции" />
        ) : null}
      </div>
      <div className={layout === "row" ? "rail-row" : "card-grid"}>
        {data.items.map((item) => (
          <EquipmentCard
            key={item.id}
            item={item}
            score={data.strategy === "content" ? item.score : undefined}
          />
        ))}
      </div>
    </div>
  );
}
