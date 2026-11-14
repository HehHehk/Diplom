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
  Row,
  Segmented,
  Select,
  Space,
  Spin,
  Tag,
  Typography,
} from "antd";
import dayjs, { Dayjs } from "dayjs";
import { api, apiError } from "../api/client";
import { combineDateTime, durationLimits, pickBillingUnit, slotsForDate } from "../booking";
import { money } from "../format";
import type { Availability, BookingPreview, Equipment, Forecast } from "../api/types";
import EquipmentRail from "../components/EquipmentRail";
import ForecastBlock from "../components/ForecastBlock";
import { useAuth } from "../auth";

export default function EquipmentPage() {
  const { id } = useParams();
  const equipmentId = Number(id);
  const { user } = useAuth();
  const { message } = App.useApp();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [date, setDate] = useState<Dayjs | null>(null);
  const [time, setTime] = useState<string | null>(null);
  const [amount, setAmount] = useState(1);
  const [amountUnit, setAmountUnit] = useState<"hour" | "day">("hour");

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

  useEffect(() => {
    if (!item) return;
    const unit = item.price_per_hour === null ? "day" : "hour";
    setAmountUnit(unit);
    setAmount(unit === "day" ? item.min_days : item.min_hours);
  }, [item?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  const slots = useMemo(() => slotsForDate(item, date), [item, date]);

  useEffect(() => {
    if (!slots.length) {
      setTime(null);
      return;
    }
    if (!time || !slots.includes(time)) setTime(slots[0]);
  }, [slots, time]);

  const start = combineDateTime(date, time);
  const end = start ? start.add(amount, amountUnit) : null;
  const autoUnit = item ? pickBillingUnit(item, amount, amountUnit) : "hour";

  const { data: preview, isFetching: previewLoading } = useQuery({
    queryKey: [
      "preview",
      equipmentId,
      start?.toISOString(),
      end?.toISOString(),
      amount,
      amountUnit,
    ],
    queryFn: async () =>
      (
        await api.post<BookingPreview>("/bookings/preview", {
          equipment_id: equipmentId,
          start_at: start!.toISOString(),
          end_at: end!.toISOString(),
          quantity: 1,
          billing_unit: autoUnit,
        })
      ).data,
    enabled: Boolean(start && end),
  });

  const effectiveUnit = useMemo(() => {
    if (!preview) return autoUnit;
    const chosen = preview.options.find((option) => option.billing_unit === autoUnit);
    if (chosen?.available) return autoUnit;
    const alternative = preview.options.find((option) => option.available);
    return alternative?.billing_unit ?? autoUnit;
  }, [preview, autoUnit]);

  const selectedOption = preview?.options.find(
    (option) => option.billing_unit === effectiveUnit,
  );

  const createBooking = useMutation({
    mutationFn: async () => {
      if (!start || !end) throw new Error("Выберите дату и время");
      return (
        await api.post("/bookings", {
          equipment_id: equipmentId,
          start_at: start.toISOString(),
          end_at: end.toISOString(),
          quantity: 1,
          billing_unit: effectiveUnit,
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

  const limits = durationLimits(item, amountUnit);
  const bothTariffs = item.price_per_hour !== null && item.price_per_day !== null;
  const canBook = Boolean(user) && Boolean(selectedOption?.available) && Boolean(start);

  const switchDurationUnit = (unit: "hour" | "day") => {
    setAmountUnit(unit);
    const next = durationLimits(item, unit);
    setAmount(Math.min(Math.max(next.min, amount), next.max));
  };

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
                {item.price_per_hour ? money(item.price_per_hour) : "—"}
              </Descriptions.Item>
              <Descriptions.Item label="Суточный тариф">
                {item.price_per_day ? money(item.price_per_day) : "—"}
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
              <div>
                <Typography.Text type="secondary">Дата выдачи</Typography.Text>
                <DatePicker
                  style={{ width: "100%" }}
                  format="DD.MM.YYYY"
                  value={date}
                  disabledDate={(current) => current.isBefore(dayjs().startOf("day"))}
                  onChange={(value) => {
                    setDate(value);
                    setTime(null);
                  }}
                />
              </div>

              <div>
                <Typography.Text type="secondary">Время выдачи</Typography.Text>
                <Select
                  style={{ width: "100%" }}
                  placeholder="Сначала выберите дату"
                  value={time}
                  disabled={!date}
                  onChange={setTime}
                  options={slots.map((slot) => ({ value: slot, label: slot }))}
                  notFoundContent="В этот день выдача не работает"
                />
              </div>

              <div>
                <Typography.Text type="secondary">Длительность</Typography.Text>
                <Space.Compact style={{ width: "100%" }}>
                  <InputNumber
                    style={{ width: "100%" }}
                    min={limits.min}
                    max={limits.max}
                    value={amount}
                    onChange={(value) => setAmount(value ?? limits.min)}
                  />
                  {bothTariffs ? (
                    <Segmented
                      value={amountUnit}
                      onChange={(value) => switchDurationUnit(value as "hour" | "day")}
                      options={[
                        { value: "hour", label: "часы" },
                        { value: "day", label: "сутки" },
                      ]}
                    />
                  ) : (
                    <span className="duration-unit">
                      {amountUnit === "day" ? "сутки" : "часы"}
                    </span>
                  )}
                </Space.Compact>
              </div>

              {start && end ? (
                <Typography.Text type="secondary">
                  {start.format("DD.MM.YYYY HH:mm")} — {end.format("DD.MM.YYYY HH:mm")}
                </Typography.Text>
              ) : null}

              {date && slots.length === 0 ? (
                <Alert type="warning" showIcon title="В этот день выдача не работает" />
              ) : null}

              {previewLoading ? <Spin /> : null}

              {preview ? (
                <div className="tariff-list">
                  {preview.options.map((option) => (
                    <div
                      key={option.billing_unit}
                      className={
                        option.billing_unit === effectiveUnit
                          ? "tariff-row tariff-row-active"
                          : "tariff-row"
                      }
                    >
                      <span>{option.billing_unit === "hour" ? "По часам" : "По суткам"}</span>
                      <b>{option.total ? money(option.total, 2) : "недоступно"}</b>
                      {option.billing_unit === effectiveUnit ? <Tag color="green">выбрано</Tag> : null}
                    </div>
                  ))}
                  <Typography.Text type="secondary">
                    Тариф выбирается автоматически по длительности аренды.
                  </Typography.Text>
                </div>
              ) : (
                <Typography.Text type="secondary">
                  Выберите дату, время и длительность — покажем стоимость.
                </Typography.Text>
              )}

              {selectedOption && selectedOption.problems.length ? (
                <Alert type="warning" showIcon title={selectedOption.problems.join("; ")} />
              ) : null}

              {selectedOption?.available ? (
                <Typography.Title level={4} style={{ margin: 0 }}>
                  Итого: {money(selectedOption.total, 2)}
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
