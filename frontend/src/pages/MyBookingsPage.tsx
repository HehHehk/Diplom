import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  App,
  Button,
  Form,
  Input,
  Modal,
  Select,
  Space,
  Table,
  Tag,
  Typography,
} from "antd";
import type { TableProps } from "antd";
import dayjs from "dayjs";
import { Link } from "react-router-dom";
import { api, apiError } from "../api/client";
import type { Booking, Page } from "../api/types";

const statusMeta: Record<Booking["status"], { label: string; color: string }> = {
  confirmed: { label: "Подтверждена", color: "blue" },
  completed: { label: "Завершена", color: "green" },
  cancelled: { label: "Отменена", color: "default" },
  terminated: { label: "Досрочно завершена", color: "orange" },
  no_show: { label: "Неявка", color: "red" },
};

type Action = { booking: Booking; kind: "cancel" | "early" | "appeal" };

const reasonOptions = {
  cancel: [
    { value: "cannot_use", label: "Не могу воспользоваться бронью" },
    { value: "emergency", label: "Личные обстоятельства / ЧП" },
    { value: "other", label: "Другое" },
  ],
  early: [
    { value: "equipment_broken", label: "Оборудование не работает" },
    { value: "equipment_damaged", label: "Оборудование повреждено" },
    { value: "emergency", label: "Личные обстоятельства / ЧП" },
    { value: "other", label: "Другое" },
  ],
  appeal: [{ value: "appeal", label: "Оспорить решение" }],
};

export default function MyBookingsPage() {
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const [action, setAction] = useState<Action | null>(null);
  const [form] = Form.useForm();

  const { data, isLoading } = useQuery({
    queryKey: ["my-bookings"],
    queryFn: async () => (await api.get<Page<Booking>>("/bookings/my?limit=100")).data,
  });

  const submit = useMutation({
    mutationFn: async (values: { reason: string; description?: string }) => {
      if (!action) return;
      const suffix =
        action.kind === "cancel" ? "cancel" : action.kind === "early" ? "early-return" : "appeal";
      return (
        await api.post(`/bookings/${action.booking.id}/${suffix}`, {
          reason: values.reason,
          description: values.description,
        })
      ).data;
    },
    onSuccess: () => {
      message.success("Готово");
      setAction(null);
      form.resetFields();
      void queryClient.invalidateQueries({ queryKey: ["my-bookings"] });
    },
    onError: (error) => message.error(apiError(error)),
  });

  const columns: TableProps<Booking>["columns"] = [
    {
      title: "Позиция",
      dataIndex: ["equipment", "title"],
      render: (_, record) => (
        <Link to={`/equipment/${record.equipment_id}`}>{record.equipment.title}</Link>
      ),
    },
    {
      title: "Период",
      render: (_, record) =>
        `${dayjs(record.start_at).format("DD.MM.YYYY HH:mm")} — ${dayjs(record.end_at).format(
          "DD.MM.YYYY HH:mm",
        )}`,
    },
    {
      title: "Статус",
      dataIndex: "status",
      render: (value: Booking["status"]) => (
        <Tag color={statusMeta[value].color}>{statusMeta[value].label}</Tag>
      ),
    },
    {
      title: "Сумма",
      dataIndex: "total_price",
      render: (value: string) => `${Number(value).toFixed(2)} ₽`,
    },
    {
      title: "Штраф / возврат",
      render: (_, record) =>
        `${Number(record.penalty_amount).toFixed(0)} / ${Number(record.refund_amount).toFixed(0)} ₽`,
    },
    {
      title: "Спор",
      dataIndex: "dispute_status",
      render: (value: Booking["dispute_status"]) =>
        value === "none" ? "—" : value === "pending" ? <Tag color="orange">на рассмотрении</Tag> : <Tag color="green">решён</Tag>,
    },
    {
      title: "Действия",
      render: (_, record) => {
        const now = dayjs();
        const money =
          Number(record.penalty_amount) +
          Number(record.compensation_amount) +
          Number(record.damage_amount);
        return (
          <Space wrap>
            {record.status === "confirmed" && !record.picked_up_at && dayjs(record.start_at).isAfter(now) ? (
              <Button size="small" onClick={() => setAction({ booking: record, kind: "cancel" })}>
                Отменить
              </Button>
            ) : null}
            {record.status === "confirmed" && record.picked_up_at ? (
              <Button size="small" onClick={() => setAction({ booking: record, kind: "early" })}>
                Досрочный возврат
              </Button>
            ) : null}
            {["cancelled", "no_show"].includes(record.status) &&
            record.dispute_status === "none" &&
            money > 0 ? (
              <Button size="small" onClick={() => setAction({ booking: record, kind: "appeal" })}>
                Оспорить
              </Button>
            ) : null}
          </Space>
        );
      },
    },
  ];

  return (
    <Space orientation="vertical" size="large" style={{ width: "100%" }}>
      <Typography.Title level={3}>Мои брони</Typography.Title>
      <Table
        rowKey="id"
        loading={isLoading}
        dataSource={data?.items ?? []}
        columns={columns}
        pagination={false}
        scroll={{ x: 900 }}
      />

      <Modal
        open={Boolean(action)}
        title={
          action?.kind === "cancel"
            ? "Отмена брони"
            : action?.kind === "early"
              ? "Досрочный возврат"
              : "Оспаривание решения"
        }
        onCancel={() => setAction(null)}
        onOk={() => form.submit()}
        confirmLoading={submit.isPending}
        okText="Отправить"
      >
        <Form form={form} layout="vertical" onFinish={(values) => submit.mutate(values)}>
          <Form.Item name="reason" label="Причина" rules={[{ required: true }]}>
            <Select options={reasonOptions[action?.kind ?? "cancel"]} />
          </Form.Item>
          <Form.Item
            name="description"
            label="Описание"
            rules={
              action?.kind === "cancel"
                ? []
                : [{ required: true, min: 50, message: "Минимум 50 символов" }]
            }
            extra="Подробно опишите ситуацию — админ увидит текст."
          >
            <Input.TextArea rows={4} maxLength={2000} showCount />
          </Form.Item>
        </Form>
      </Modal>
    </Space>
  );
}
