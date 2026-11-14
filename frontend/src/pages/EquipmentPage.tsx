import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  App,
  Button,
  Card,
  Col,
  DatePicker,
  Descriptions,
  Divider,
  Empty,
  InputNumber,
  Radio,
  Row,
  Space,
  Spin,
  Tag,
  Typography,
} from "antd";
import dayjs, { Dayjs } from "dayjs";
import { api, apiError } from "../api/client";
import type {
  Availability,
  BillingUnit,
  BookingPreview,
  Equipment,
  Forecast,
} from "../api/types";
import EquipmentRail from "../components/EquipmentRail";
import ForecastBlock from "../components/ForecastBlock";
import { useAuth } from "../auth";

const { RangePicker } = DatePicker;

export default function EquipmentPage() {
  const { id } = useParams();
  const equipmentId = Number(id);
  const { user } = useAuth();
  const { message } = App.useApp();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [range, setRange] = useState<[Dayjs, Dayjs] | null>(null);
  const [quantity, setQuantity] = useState(1);
  const [unit, setUnit] = useState<BillingUnit>("day");

  const { data: item, isLoading } = useQuery({
    queryKey: ["equipment", equipmentId],
    queryFn: async () => (await api.get<Equipment>(`/equipment/${equipmentId}`)).data,
  });

  const { data: forecast } = useQuery({
    queryKey: ["forecast", equipmentId],
    queryFn: async () =>
      (await api.get<Forecast>(`/equipment/${equipmentId}/load-forecast?days=90`)).data,
  });

  const { data: availability } = useQuery({
    queryKey: ["availability", equipmentId],
    queryFn: async () => {
      const from = dayjs().toISOString();
      const to = dayjs().add(30, "day").toISOString();
      return (
        await api.get<Availability>(
          `/equipment/${equipmentId}/availability?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`,
        )
      ).data;
    },
  });

  const start = range?.[0];
  const end = range?.[1];

  const { data: preview, isFetching: previewLoading } = useQuery({
    queryKey: ["preview", equipmentId, start?.toISOString(), end?.toISOString(), quantity],
    queryFn: async () =>
      (
        await api.post<BookingPreview>("/bookings/preview", {
          equipment_id: equipmentId,
          start_at: start!.toISOString(),
          end_at: end!.toISOString(),
          quantity,
          billing_unit: unit,
        })
      ).data,
    enabled: Boolean(start && end),
  });

  useEffect(() => {
    if (preview?.recommended && !range) return;
    if (preview?.recommended) setUnit(preview.recommended);
  }, [preview?.recommended, range]);

  const selectedOption = useMemo(
    () => preview?.options.find((option) => option.billing_unit === unit),
    [preview, unit],
  );

  const createBooking = useMutation({
    mutationFn: async () => {
      if (!start || !end) throw new Error("Выберите период");
      return (
        await api.post("/bookings", {
          equipment_id: equipmentId,
          start_at: start.toISOString(),
          end_at: end.toISOString(),
          quantity,
          billing_unit: unit,
        })
      ).data;
    },
    onSuccess: () => {
      message.success("Бронь создана");
      void queryClient.invalidateQueries({ queryKey: ["availability", equipmentId] });
      navigate("/my");
    },
    onError: (error) => message.error(apiError(error)),
  });

  if (isLoading) return <Spin size="large" />;
  if (!item) return <Empty description="Позиция не найдена" />;

  const canBook = Boolean(user) && Boolean(selectedOption?.available);

  return (
    <Space orientation="vertical" size="large" style={{ width: "100%" }}>
      <Link to="/">← Назад в каталог</Link>

      <Row gutter={[24, 24]}>
        <Col xs={24} lg={14}>
          <Card>
            <div className="detail-cover">{item.category}</div>
            <Typography.Title level={2}>{item.title}</Typography.Title>
            <Space wrap>
              <Tag color="blue">{item.brand || "без бренда"}</Tag>
              <Tag>{item.category}</Tag>
              <Tag>В наличии: {item.quantity}</Tag>
              {item.working_hours ? <Tag color="orange">по графику</Tag> : <Tag color="green">24/7</Tag>}
            </Space>
            <Typography.Paragraph style={{ marginTop: 16 }}>
              {item.description || "Описание не заполнено."}
            </Typography.Paragraph>
            <Descriptions column={2} size="small">
              <Descriptions.Item label="Часовой тариф">
                {item.price_per_hour ? `${Number(item.price_per_hour).toFixed(0)} ₽` : "—"}
              </Descriptions.Item>
              <Descriptions.Item label="Суточный тариф">
                {item.price_per_day ? `${Number(item.price_per_day).toFixed(0)} ₽` : "—"}
              </Descriptions.Item>
              <Descriptions.Item label="Минимум">
                {item.min_hours} ч / {item.min_days} сут
              </Descriptions.Item>
              <Descriptions.Item label="Максимум">
                {item.max_hours} ч / {item.max_days} сут
              </Descriptions.Item>
              <Descriptions.Item label="Буфер">{item.buffer_minutes} мин</Descriptions.Item>
              <Descriptions.Item label="Часовой пояс">{item.timezone}</Descriptions.Item>
            </Descriptions>
          </Card>

          {forecast ? (
            <Card title="Прогноз загрузки" style={{ marginTop: 16 }}>
              <ForecastBlock forecast={forecast} />
            </Card>
          ) : null}

          {availability?.busy.length ? (
            <Card title="Ближайшие занятые периоды" style={{ marginTop: 16 }}>
              <Space orientation="vertical">
                {availability.busy.slice(0, 8).map((slot) => (
                  <Typography.Text key={`${slot.start_at}-${slot.end_at}`}>
                    {dayjs(slot.start_at).format("DD.MM HH:mm")} —{" "}
                    {dayjs(slot.end_at).format("DD.MM HH:mm")} · {slot.quantity} шт.
                  </Typography.Text>
                ))}
              </Space>
            </Card>
          ) : null}
        </Col>

        <Col xs={24} lg={10}>
          <Card title="Забронировать">
            <Space orientation="vertical" size="middle" style={{ width: "100%" }}>
              <RangePicker
                showTime={{ minuteStep: 30 }}
                format="DD.MM.YYYY HH:mm"
                style={{ width: "100%" }}
                value={range}
                onChange={(values) => setRange(values as [Dayjs, Dayjs] | null)}
              />
              <Space>
                <Typography.Text>Количество</Typography.Text>
                <InputNumber
                  min={1}
                  max={item.quantity}
                  value={quantity}
                  onChange={(value) => setQuantity(value ?? 1)}
                />
              </Space>

              {previewLoading ? <Spin /> : null}

              {preview ? (
                <Radio.Group
                  value={unit}
                  onChange={(event) => setUnit(event.target.value)}
                  style={{ width: "100%" }}
                >
                  <Space orientation="vertical" style={{ width: "100%" }}>
                    {preview.options.map((option) => (
                      <Radio key={option.billing_unit} value={option.billing_unit}>
                        {option.billing_unit === "hour" ? "По часам" : "По суткам"}
                        {option.total
                          ? ` — ${Number(option.total).toFixed(2)} ₽ (${option.units} ед.)`
                          : ""}
                        {preview.recommended === option.billing_unit ? " · выгодно" : ""}
                        {!option.available ? " · недоступно" : ""}
                      </Radio>
                    ))}
                  </Space>
                </Radio.Group>
              ) : (
                <Typography.Text type="secondary">
                  Выберите период — покажем оба тарифа и стоимость.
                </Typography.Text>
              )}

              {selectedOption && selectedOption.problems.length ? (
                <Alert
                  type="warning"
                  showIcon
                  title={selectedOption.problems.join("; ")}
                />
              ) : null}

              {selectedOption?.available ? (
                <Typography.Title level={4} style={{ margin: 0 }}>
                  Итого: {Number(selectedOption.total).toFixed(2)} ₽
                </Typography.Title>
              ) : null}

              <Divider style={{ margin: "8px 0" }} />

              {user ? (
                <Button
                  type="primary"
                  size="large"
                  block
                  loading={createBooking.isPending}
                  disabled={!canBook}
                  onClick={() => createBooking.mutate()}
                >
                  Забронировать
                </Button>
              ) : (
                <Button type="primary" size="large" block onClick={() => navigate("/login")}>
                  Войдите, чтобы забронировать
                </Button>
              )}
            </Space>
          </Card>
        </Col>
      </Row>

      <EquipmentRail
        title="Похожие позиции"
        source={{ kind: "recommendations", equipmentId }}
      />
    </Space>
  );
}
