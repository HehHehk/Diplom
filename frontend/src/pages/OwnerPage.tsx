import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  App,
  Button,
  Card,
  Col,
  Form,
  Input,
  InputNumber,
  Modal,
  Popconfirm,
  Row,
  Segmented,
  Select,
  Space,
  Statistic,
  Switch,
  Table,
  Tabs,
  Tag,
  Typography,
} from "antd";
import type { TableProps } from "antd";
import dayjs from "dayjs";
import { api, apiError } from "../api/client";
import { money } from "../format";
import type { Booking, Category, Equipment, OwnerStats, Page } from "../api/types";

const WEEKDAYS = [
  { key: "mon", label: "Пн" },
  { key: "tue", label: "Вт" },
  { key: "wed", label: "Ср" },
  { key: "thu", label: "Чт" },
  { key: "fri", label: "Пт" },
  { key: "sat", label: "Сб" },
  { key: "sun", label: "Вс" },
] as const;

const TIME_OPTIONS = Array.from({ length: 48 }, (_, index) => {
  const minutes = index * 30;
  const value = `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(
    minutes % 60,
  ).padStart(2, "0")}`;
  return { value, label: value };
});

interface DaySchedule {
  enabled: boolean;
  open: string;
  close: string;
}

function defaultSchedule(): Record<string, DaySchedule> {
  return {
    mon: { enabled: true, open: "09:00", close: "20:00" },
    tue: { enabled: true, open: "09:00", close: "20:00" },
    wed: { enabled: true, open: "09:00", close: "20:00" },
    thu: { enabled: true, open: "09:00", close: "20:00" },
    fri: { enabled: true, open: "09:00", close: "20:00" },
    sat: { enabled: true, open: "10:00", close: "18:00" },
    sun: { enabled: false, open: "10:00", close: "18:00" },
  };
}

const statusLabel: Record<Booking["status"], string> = {
  confirmed: "Подтверждена",
  completed: "Завершена",
  cancelled: "Отменена",
  terminated: "Досрочно",
  no_show: "Неявка",
};

export default function OwnerPage() {
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const [equipmentForm] = Form.useForm();
  const [returnForm] = Form.useForm();
  const damageReported = Form.useWatch("damage_reported", returnForm);
  const [editing, setEditing] = useState<Equipment | null>(null);
  const [equipmentModal, setEquipmentModal] = useState(false);
  const [returning, setReturning] = useState<Booking | null>(null);
  const [scheduleMode, setScheduleMode] = useState<"always" | "schedule">("schedule");
  const [schedule, setSchedule] = useState<Record<string, DaySchedule>>(defaultSchedule);
  const [newCategory, setNewCategory] = useState("");
  const [pendingCategory, setPendingCategory] = useState<string | null>(null);

  const { data: stats } = useQuery({
    queryKey: ["owner-stats"],
    queryFn: async () => (await api.get<OwnerStats>("/owner/stats")).data,
  });

  const { data: categories } = useQuery({
    queryKey: ["categories"],
    queryFn: async () => (await api.get<Category[]>("/categories")).data,
  });

  const createCategory = useMutation({
    mutationFn: async (name: string) => (await api.post<Category>("/categories", { name })).data,
    onSuccess: (category) => {
      message.success("Категория добавлена");
      setNewCategory("");
      setPendingCategory(category.name);
      void queryClient.invalidateQueries({ queryKey: ["categories"] });
    },
    onError: (error) => message.error(apiError(error)),
  });

  useEffect(() => {
    if (!pendingCategory) return;
    if (!categories?.some((category) => category.name === pendingCategory)) return;
    equipmentForm.setFieldsValue({ category: pendingCategory });
    setPendingCategory(null);
  }, [pendingCategory, categories, equipmentForm]);

  const { data: equipment, isLoading: equipmentLoading } = useQuery({
    queryKey: ["owner-equipment"],
    queryFn: async () => (await api.get<Page<Equipment>>("/owner/equipment?limit=100")).data,
  });

  const { data: bookings, isLoading: bookingsLoading } = useQuery({
    queryKey: ["owner-bookings"],
    queryFn: async () => (await api.get<Page<Booking>>("/owner/bookings?limit=100")).data,
  });

  const refresh = () => {
    void queryClient.invalidateQueries({ queryKey: ["owner-equipment"] });
    void queryClient.invalidateQueries({ queryKey: ["owner-bookings"] });
    void queryClient.invalidateQueries({ queryKey: ["owner-stats"] });
  };

  const buildWorkingHours = () => {
    if (scheduleMode === "always") return null;
    const result: Record<string, string[][]> = {};
    for (const day of WEEKDAYS) {
      const value = schedule[day.key];
      result[day.key] = value.enabled ? [[value.open, value.close]] : [];
    }
    return result;
  };

  const validateSchedule = (): string | null => {
    if (scheduleMode === "always") return null;
    for (const day of WEEKDAYS) {
      const value = schedule[day.key];
      if (value.enabled && value.open >= value.close) {
        return `В дне «${day.label}» открытие должно быть раньше закрытия`;
      }
    }
    return null;
  };

  const saveEquipment = useMutation({
    mutationFn: async (values: Record<string, unknown>) => {
      const payload = { ...values, working_hours: buildWorkingHours() };
      if (editing) {
        return (await api.patch(`/owner/equipment/${editing.id}`, payload)).data;
      }
      return (await api.post("/owner/equipment", payload)).data;
    },
    onSuccess: () => {
      message.success(editing ? "Позиция обновлена" : "Позиция создана");
      setEquipmentModal(false);
      setEditing(null);
      equipmentForm.resetFields();
      refresh();
    },
    onError: (error) => message.error(apiError(error)),
  });

  const submitEquipment = () => {
    const error = validateSchedule();
    if (error) {
      message.error(error);
      return;
    }
    equipmentForm.submit();
  };

  const deleteEquipment = useMutation({
    mutationFn: async (id: number) => api.delete(`/owner/equipment/${id}`),
    onSuccess: () => {
      message.success("Позиция скрыта из каталога");
      refresh();
    },
    onError: (error) => message.error(apiError(error)),
  });

  const bookingAction = useMutation({
    mutationFn: async ({
      id,
      action,
      body,
    }: {
      id: number;
      action: "pickup" | "return" | "no-show";
      body?: Record<string, unknown>;
    }) => (await api.post(`/bookings/${id}/${action}`, body ?? {})).data,
    onSuccess: () => {
      message.success("Готово");
      setReturning(null);
      returnForm.resetFields();
      refresh();
    },
    onError: (error) => message.error(apiError(error)),
  });

  const openCreate = () => {
    setEditing(null);
    equipmentForm.resetFields();
    equipmentForm.setFieldsValue({
      timezone: "Europe/Moscow",
      min_hours: 1,
      min_days: 1,
      max_hours: 24,
      max_days: 30,
      quantity: 1,
      buffer_minutes: 30,
      lead_time_minutes: 30,
    });
    setScheduleMode("schedule");
    setSchedule(defaultSchedule());
    setEquipmentModal(true);
  };

  const openEdit = (item: Equipment) => {
    setEditing(item);
    const hours = item.working_hours as Record<string, string[][]> | null;
    if (!hours) {
      setScheduleMode("always");
      setSchedule(defaultSchedule());
    } else {
      setScheduleMode("schedule");
      const next = defaultSchedule();
      for (const day of WEEKDAYS) {
        const intervals = hours[day.key] ?? [];
        next[day.key] = intervals.length
          ? { enabled: true, open: intervals[0][0], close: intervals[0][1] }
          : { ...next[day.key], enabled: false };
      }
      setSchedule(next);
    }
    equipmentForm.setFieldsValue({
      ...item,
      price_per_hour: item.price_per_hour ? Number(item.price_per_hour) : null,
      price_per_day: item.price_per_day ? Number(item.price_per_day) : null,
    });
    setEquipmentModal(true);
  };

  const updateDay = (key: string, patch: Partial<DaySchedule>) => {
    setSchedule((previous) => ({
      ...previous,
      [key]: { ...previous[key], ...patch },
    }));
  };

  const equipmentColumns: TableProps<Equipment>["columns"] = [
    { title: "Название", dataIndex: "title" },
    { title: "Категория", dataIndex: "category" },
    {
      title: "Тарифы",
      render: (_, record) =>
        `${record.price_per_hour ? `${money(record.price_per_hour)}/ч` : "—"} · ${
          record.price_per_day ? `${money(record.price_per_day)}/сут` : "—"
        }`,
    },
    { title: "Кол-во", dataIndex: "quantity" },
    {
      title: "Статус",
      dataIndex: "is_active",
      render: (value: boolean) => (value ? <Tag color="green">активна</Tag> : <Tag>скрыта</Tag>),
    },
    {
      title: "Действия",
      render: (_, record) => (
        <Space>
          <Button size="small" onClick={() => openEdit(record)}>
            Изменить
          </Button>
          <Popconfirm
            title="Скрыть позицию из каталога?"
            onConfirm={() => deleteEquipment.mutate(record.id)}
          >
            <Button size="small" danger>
              Скрыть
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  const bookingColumns: TableProps<Booking>["columns"] = [
    { title: "Позиция", dataIndex: ["equipment", "title"] },
    {
      title: "Период",
      render: (_, record) =>
        `${dayjs(record.start_at).format("DD.MM HH:mm")} — ${dayjs(record.end_at).format(
          "DD.MM HH:mm",
        )}`,
    },
    { title: "Кол-во", dataIndex: "quantity" },
    {
      title: "Статус",
      dataIndex: "status",
      render: (value: Booking["status"]) => <Tag>{statusLabel[value]}</Tag>,
    },
    {
      title: "Сумма",
      dataIndex: "total_price",
      render: (value: string) => money(value),
    },
    {
      title: "Действия",
      render: (_, record) => (
        <Space wrap>
          {record.status === "confirmed" && !record.picked_up_at ? (
            <>
              <Button
                size="small"
                type="primary"
                onClick={() => bookingAction.mutate({ id: record.id, action: "pickup" })}
              >
                Выдать
              </Button>
              <Button
                size="small"
                onClick={() => bookingAction.mutate({ id: record.id, action: "no-show" })}
              >
                Неявка
              </Button>
            </>
          ) : null}
          {record.status === "confirmed" && record.picked_up_at ? (
            <Button size="small" onClick={() => setReturning(record)}>
              Вернуть
            </Button>
          ) : null}
        </Space>
      ),
    },
  ];

  return (
    <Space orientation="vertical" size="large" style={{ width: "100%" }}>
      <Typography.Title level={3}>Кабинет арендодателя</Typography.Title>

      <Row gutter={[16, 16]}>
        <Col xs={12} md={6}>
          <Card>
            <Statistic title="Позиций" value={stats?.equipment_total ?? 0} suffix={`/ ${stats?.equipment_active ?? 0} активных`} loading={!stats} />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card>
            <Statistic title="Активных броней" value={stats?.bookings_active ?? 0} loading={!stats} />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card>
            <Statistic
              title="Выручка"
              value={Number(stats?.revenue ?? 0)}
              formatter={(value) => money(value)}
              loading={!stats}
            />
          </Card>
        </Col>
        <Col xs={12} md={6}>
          <Card>
            <Statistic title="Споров" value={stats?.disputes_pending ?? 0} loading={!stats} />
          </Card>
        </Col>
      </Row>

      <Tabs
        items={[
          {
            key: "equipment",
            label: "Мои позиции",
            children: (
              <Space orientation="vertical" style={{ width: "100%" }}>
                <Button type="primary" onClick={openCreate}>
                  Добавить позицию
                </Button>
                <Table
                  rowKey="id"
                  loading={equipmentLoading}
                  dataSource={equipment?.items ?? []}
                  columns={equipmentColumns}
                  pagination={false}
                  scroll={{ x: 800 }}
                  locale={{ emptyText: "Добавьте первую позицию — она сразу появится в каталоге" }}
                />
              </Space>
            ),
          },
          {
            key: "bookings",
            label: "Брони",
            children: (
              <Table
                rowKey="id"
                loading={bookingsLoading}
                dataSource={bookings?.items ?? []}
                columns={bookingColumns}
                pagination={false}
                scroll={{ x: 900 }}
                locale={{ emptyText: "Броней пока нет" }}
              />
            ),
          },
        ]}
      />

      <Modal
        open={equipmentModal}
        title={editing ? "Редактирование позиции" : "Новая позиция"}
        onCancel={() => setEquipmentModal(false)}
        onOk={submitEquipment}
        confirmLoading={saveEquipment.isPending}
        width={720}
        okText="Сохранить"
      >
        <Form form={equipmentForm} layout="vertical" onFinish={(values) => saveEquipment.mutate(values)}>
          <Row gutter={12}>
            <Col span={12}>
              <Form.Item name="title" label="Название" rules={[{ required: true }]}>
                <Input />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="category" label="Категория" rules={[{ required: true }]}>
                <Select
                  showSearch
                  optionFilterProp="label"
                  placeholder="Выберите категорию"
                  options={(categories ?? []).map((category) => ({
                    value: category.name,
                    label: category.name,
                  }))}
                />
              </Form.Item>
              <Space.Compact style={{ width: "100%", marginTop: -12, marginBottom: 12 }}>
                <Input
                  placeholder="Новая категория"
                  value={newCategory}
                  onChange={(event) => setNewCategory(event.target.value)}
                />
                <Button
                  onClick={() => createCategory.mutate(newCategory.trim())}
                  disabled={!newCategory.trim()}
                  loading={createCategory.isPending}
                >
                  Добавить
                </Button>
              </Space.Compact>
            </Col>
            <Col span={12}>
              <Form.Item name="brand" label="Бренд">
                <Input />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="quantity" label="Количество" rules={[{ required: true }]}>
                <InputNumber min={0} style={{ width: "100%" }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="price_per_hour" label="Цена за час, Br">
                <InputNumber min={0} style={{ width: "100%" }} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="price_per_day" label="Цена за сутки, Br">
                <InputNumber min={0} style={{ width: "100%" }} />
              </Form.Item>
            </Col>
            <Col span={6}>
              <Form.Item name="min_hours" label="Мин. часов">
                <InputNumber min={1} style={{ width: "100%" }} />
              </Form.Item>
            </Col>
            <Col span={6}>
              <Form.Item name="max_hours" label="Макс. часов">
                <InputNumber min={1} style={{ width: "100%" }} />
              </Form.Item>
            </Col>
            <Col span={6}>
              <Form.Item name="min_days" label="Мин. суток">
                <InputNumber min={1} style={{ width: "100%" }} />
              </Form.Item>
            </Col>
            <Col span={6}>
              <Form.Item name="max_days" label="Макс. суток">
                <InputNumber min={1} style={{ width: "100%" }} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="buffer_minutes" label="Буфер, мин">
                <InputNumber min={0} style={{ width: "100%" }} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="lead_time_minutes" label="Запас до выдачи, мин">
                <InputNumber min={0} style={{ width: "100%" }} />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item name="timezone" label="Часовой пояс">
                <Input />
              </Form.Item>
            </Col>
            <Col span={24}>
              <Form.Item name="description" label="Описание">
                <Input.TextArea rows={2} />
              </Form.Item>
            </Col>
            <Col span={24}>
              <Form.Item label="Режим выдачи">
                <Segmented
                  value={scheduleMode}
                  onChange={(value) => setScheduleMode(value as "always" | "schedule")}
                  options={[
                    { value: "schedule", label: "По графику" },
                    { value: "always", label: "Круглосуточно" },
                  ]}
                />
              </Form.Item>
            </Col>
            {scheduleMode === "schedule" ? (
              <Col span={24}>
                <div className="schedule-editor">
                  {WEEKDAYS.map((day) => (
                    <div className="schedule-row" key={day.key}>
                      <Switch
                        checked={schedule[day.key].enabled}
                        onChange={(checked) => updateDay(day.key, { enabled: checked })}
                      />
                      <span className="schedule-day">{day.label}</span>
                      <Select
                        value={schedule[day.key].open}
                        options={TIME_OPTIONS}
                        disabled={!schedule[day.key].enabled}
                        onChange={(value) => updateDay(day.key, { open: value })}
                        style={{ width: 100 }}
                      />
                      <span>—</span>
                      <Select
                        value={schedule[day.key].close}
                        options={TIME_OPTIONS}
                        disabled={!schedule[day.key].enabled}
                        onChange={(value) => updateDay(day.key, { close: value })}
                        style={{ width: 100 }}
                      />
                    </div>
                  ))}
                </div>
              </Col>
            ) : null}
          </Row>
        </Form>
      </Modal>

      <Modal
        open={Boolean(returning)}
        title="Возврат оборудования"
        onCancel={() => setReturning(null)}
        onOk={() => returnForm.submit()}
        confirmLoading={bookingAction.isPending}
        okText="Оформить возврат"
      >
        <Form
          form={returnForm}
          layout="vertical"
          initialValues={{ damage_reported: false }}
          onFinish={(values) =>
            returning &&
            bookingAction.mutate({
              id: returning.id,
              action: "return",
              body: values,
            })
          }
        >
          <Form.Item name="damage_reported" label="Есть повреждения" valuePropName="checked">
            <Switch />
          </Form.Item>
          <Form.Item
            name="description"
            label="Комментарий"
            rules={
              damageReported
                ? [{ required: true, min: 50, message: "Минимум 50 символов для спора" }]
                : []
            }
          >
            <Input.TextArea rows={3} />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  );
}
