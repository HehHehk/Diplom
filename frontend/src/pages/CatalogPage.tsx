import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Col, Empty, Input, Pagination, Row, Select, Space, Spin, Typography } from "antd";
import { api } from "../api/client";
import type { Category, Equipment, Page } from "../api/types";
import EquipmentCard from "../components/EquipmentCard";
import EquipmentRail from "../components/EquipmentRail";

const PAGE_SIZE = 12;

export default function CatalogPage() {
  const [q, setQ] = useState("");
  const [category, setCategory] = useState<string | undefined>();
  const [sort, setSort] = useState("newest");
  const [page, setPage] = useState(1);

  const { data: categories } = useQuery({
    queryKey: ["categories"],
    queryFn: async () => (await api.get<Category[]>("/categories")).data,
  });

  const { data, isLoading } = useQuery({
    queryKey: ["equipment", q, category, sort, page],
    queryFn: async () => {
      const params = new URLSearchParams({
        limit: String(PAGE_SIZE),
        offset: String((page - 1) * PAGE_SIZE),
        sort,
      });
      if (q.trim()) params.set("q", q.trim());
      if (category) params.set("category", category);
      return (await api.get<Page<Equipment>>(`/equipment?${params.toString()}`)).data;
    },
  });

  return (
    <Space orientation="vertical" size="large" style={{ width: "100%" }}>
      <section className="hero">
        <Typography.Title level={2}>Аренда оборудования без звонков и переписок</Typography.Title>
        <Typography.Paragraph>
          Каталог с умным подбором, проверкой пересечений и прогнозом загрузки.
        </Typography.Paragraph>
        <Input.Search
          size="large"
          allowClear
          placeholder="Найти перфоратор, палатку, мойку…"
          onSearch={(value) => {
            setQ(value);
            setPage(1);
          }}
          enterButton="Найти"
        />
      </section>

      {!q.trim() ? (
        <EquipmentRail
          title="Популярное сейчас"
          source={{ kind: "popular" }}
          layout="row"
        />
      ) : null}

      <div className="catalog-toolbar">
        <Select
          allowClear
          placeholder="Категория"
          style={{ minWidth: 220 }}
          value={category}
          onChange={(value) => {
            setCategory(value);
            setPage(1);
          }}
          options={(categories ?? []).map((item) => ({ value: item.name, label: item.name }))}
        />
        <Select
          value={sort}
          style={{ minWidth: 200 }}
          onChange={(value) => {
            setSort(value);
            setPage(1);
          }}
          options={[
            { value: "newest", label: "Сначала новые" },
            { value: "price_asc", label: "Цена: по возрастанию" },
            { value: "price_desc", label: "Цена: по убыванию" },
            { value: "title", label: "По названию" },
          ]}
        />
        <Typography.Text type="secondary">
          {data ? `Найдено: ${data.total}` : "Загрузка…"}
        </Typography.Text>
      </div>

      {isLoading ? (
        <Spin size="large" />
      ) : data && data.items.length ? (
        <>
          <Row gutter={[16, 16]}>
            {data.items.map((item) => (
              <Col key={item.id} xs={24} sm={12} lg={8} xl={6}>
                <EquipmentCard item={item} />
              </Col>
            ))}
          </Row>
          <Pagination
            current={page}
            pageSize={PAGE_SIZE}
            total={data.total}
            onChange={setPage}
            showSizeChanger={false}
          />
        </>
      ) : (
        <Empty description="Ничего не найдено — попробуйте изменить фильтры" />
      )}
    </Space>
  );
}
