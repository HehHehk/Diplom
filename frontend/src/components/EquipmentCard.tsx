import { Card, Tag, Typography, Space } from "antd";
import { Link } from "react-router-dom";
import type { Equipment } from "../api/types";
import { money } from "../format";

function priceLabel(item: Equipment): string {
  if (item.price_per_day && item.price_per_hour) {
    return `${money(item.price_per_hour)}/час · ${money(item.price_per_day)}/сутки`;
  }
  if (item.price_per_hour) return `${money(item.price_per_hour)}/час`;
  if (item.price_per_day) return `${money(item.price_per_day)}/сутки`;
  return "цена не задана";
}

export default function EquipmentCard({
  item,
  score,
}: {
  item: Equipment;
  score?: number;
}) {
  return (
    <Link to={`/equipment/${item.id}`} className="card-link">
      <Card hoverable className="equipment-card">
        <div className="card-cover">
          <span>{item.category}</span>
          {item.image_url ? <img src={item.image_url} alt={item.title} /> : null}
        </div>
        <Typography.Title level={5} className="card-title">
          {item.title}
        </Typography.Title>
        <Space size={4} wrap>
          <Tag color="blue">{item.brand || "без бренда"}</Tag>
          <Tag>{item.quantity} шт.</Tag>
          {typeof score === "number" && score > 0 ? (
            <Tag color="green">релевантность {(score * 100).toFixed(0)}%</Tag>
          ) : null}
        </Space>
        <div className="card-price">{priceLabel(item)}</div>
      </Card>
    </Link>
  );
}
