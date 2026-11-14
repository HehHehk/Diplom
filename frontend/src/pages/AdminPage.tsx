import { useState } from "react";
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
  Row,
  Select,
  Space,
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
import type { AdminUser, Dispute, Page } from "../api/types";

const outcomeOptions = [
  { value: "client_fault", label: "Вина клиента" },
  { value: "owner_fault", label: "Вина арендодателя" },
  { value: "equipment_fault", label: "Неисправность оборудования" },
  { value: "force_majeure", label: "Форс-мажор" },
  { value: "no_fault", label: "Никто не виноват" },
];

export default function AdminPage() {
  const { message } = App.useApp();
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<"pending" | "resolved" | "all">("pending");
  const [selected, setSelected] = useState<Dispute | null>(null);
  const [form] = Form.useForm();

  const { data: disputes, isLoading: disputesLoading } = useQuery({
    queryKey: ["admin-disputes", status],
    queryFn: async () =>
      (await api.get<Page<Dispute>>(`/admin/disputes?status=${status}&limit=100`)).data,
  });

  const { data: users, isLoading: usersLoading } = useQuery({
    queryKey: ["admin-users"],
    queryFn: async () => (await api.get<Page<AdminUser>>("/admin/users?limit=100")).data,
  });

  const resolve = useMutation({
    mutationFn: async (values: Record<string, unknown>) => {
      if (!selected) return;
      const payload: Record<string, unknown> = { outcome: values.outcome };
      for (const key of ["penalty_amount", "refund_amount", "compensation_amount", "damage_amount"]) {
        if (values[key] !== undefined && values[key] !== null) payload[key] = values[key];
      }
      if (values.comment) payload.comment = values.comment;
      return (await api.post(`/admin/disputes/${selected.booking_id}/resolve`, payload)).data;
    },
    onSuccess: () => {
      message.success("Решение сохранено");
      setSelected(null);
      form.resetFields();
      void queryClient.invalidateQueries({ queryKey: ["admin-disputes"] });
    },
    onError: (error) => message.error(apiError(error)),
  });

  const patchUser = useMutation({
    mutationFn: async ({ id, body }: { id: number; body: Record<string, unknown> }) =>
      (await api.patch(`/admin/users/${id}`, body)).data,
    onSuccess: () => {
      message.success("Пользователь обновлён");
      void queryClient.invalidateQueries({ queryKey: ["admin-users"] });
    },
    onError: (error) => message.error(apiError(error)),
  });

  const disputeColumns: TableProps<Dispute>["columns"] = [
    { title: "Бронь", dataIndex: "booking_id", width: 80 },
    { title: "Позиция", dataIndex: "equipment_title" },
    {
      title: "Стороны",
      render: (_, record) => (
        <Space orientation="vertical" size={0}>
          <Typography.Text>{record.client_email}</Typography.Text>
          <Typography.Text type="secondary">{record.owner_email ?? "—"}</Typography.Text>
        </Space>
      ),
    },
    { title: "Причина", dataIndex: "reason" },
    {
      title: "Создан",
      dataIndex: "created_at",
      render: (value: string | null) => (value ? dayjs(value).format("DD.MM HH:mm") : "—"),
    },
    {
      title: "Сумма",
      dataIndex: "total_price",
      render: (value: string) => money(value),
    },
    {
      title: "Статус",
      render: (_, record) =>
        record.status === "pending" ? (
          <Tag color="orange">ожидает</Tag>
        ) : (
          <Tag color="green">{record.outcome ?? "решён"}</Tag>
        ),
    },
    {
      title: "Действия",
      render: (_, record) =>
        record.status === "pending" ? (
          <Button
            size="small"
            type="primary"
            onClick={() => {
              setSelected(record);
              form.resetFields();
            }}
          >
            Решить
          </Button>
        ) : null,
    },
  ];

  const userColumns: TableProps<AdminUser>["columns"] = [
    { title: "Email", dataIndex: "email" },
    { title: "Имя", dataIndex: "full_name" },
    {
      title: "Роль",
      dataIndex: "role",
      render: (value: string, record) => (
        <Select
          size="small"
          value={value}
          style={{ width: 120 }}
          onChange={(role) => patchUser.mutate({ id: record.id, body: { role } })}
          options={[
            { value: "user", label: "Клиент" },
            { value: "owner", label: "Арендодатель" },
            { value: "admin", label: "Админ" },
          ]}
        />
      ),
    },
    {
      title: "Активен",
      dataIndex: "is_active",
      render: (value: boolean, record) => (
        <Switch
          checked={value}
          onChange={(checked) => patchUser.mutate({ id: record.id, body: { is_active: checked } })}
        />
      ),
    },
    {
      title: "Нарушитель",
      dataIndex: "is_abuser",
      render: (value: boolean, record) => (
        <Switch
          checked={value}
          onChange={(checked) => patchUser.mutate({ id: record.id, body: { is_abuser: checked } })}
        />
      ),
    },
    {
      title: "Счётчики",
      render: (_, record) => (
        <Typography.Text type="secondary">
          штрафы {record.penalties_count} · отмены {record.cancellations_count} · споры{" "}
          {record.disputes_open}
        </Typography.Text>
      ),
    },
  ];

  return (
    <Space orientation="vertical" size="large" style={{ width: "100%" }}>
      <Typography.Title level={3}>Администрирование</Typography.Title>
      <Tabs
        items={[
          {
            key: "disputes",
            label: "Споры",
            children: (
              <Card>
                <Space style={{ marginBottom: 16 }}>
                  <Select
                    value={status}
                    onChange={setStatus}
                    style={{ width: 200 }}
                    options={[
                      { value: "pending", label: "Ожидают решения" },
                      { value: "resolved", label: "Решённые" },
                      { value: "all", label: "Все" },
                    ]}
                  />
                </Space>
                <Table
                  rowKey="booking_id"
                  loading={disputesLoading}
                  dataSource={disputes?.items ?? []}
                  columns={disputeColumns}
                  pagination={false}
                  scroll={{ x: 1000 }}
                  locale={{ emptyText: "Очередь споров пуста" }}
                />
              </Card>
            ),
          },
          {
            key: "users",
            label: "Пользователи",
            children: (
              <Card>
                <Table
                  rowKey="id"
                  loading={usersLoading}
                  dataSource={users?.items ?? []}
                  columns={userColumns}
                  pagination={false}
                  scroll={{ x: 1000 }}
                  locale={{ emptyText: "Пользователи не найдены" }}
                />
              </Card>
            ),
          },
        ]}
      />

      <Modal
        open={Boolean(selected)}
        title={`Спор по брони №${selected?.booking_id ?? ""}`}
        onCancel={() => setSelected(null)}
        onOk={() => form.submit()}
        confirmLoading={resolve.isPending}
        okText="Сохранить решение"
        width={640}
      >
        {selected ? (
          <Space orientation="vertical" style={{ width: "100%" }}>
            <Typography.Paragraph>
              <b>{selected.equipment_title}</b>
              <br />
              Клиент: {selected.client_email} · Арендодатель: {selected.owner_email ?? "—"}
            </Typography.Paragraph>
            <Typography.Paragraph type="secondary">
              {selected.description ?? "Описание не указано"}
            </Typography.Paragraph>
            <Typography.Text>
              Стоимость: {money(selected.total_price, 2)}
            </Typography.Text>
            <Form form={form} layout="vertical" onFinish={(values) => resolve.mutate(values)}>
              <Form.Item name="outcome" label="Решение" rules={[{ required: true }]}>
                <Select options={outcomeOptions} />
              </Form.Item>
              <Row gutter={12}>
                <Col span={12}>
                  <Form.Item name="penalty_amount" label="Штраф, Br">
                    <InputNumber min={0} style={{ width: "100%" }} />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name="refund_amount" label="Возврат, Br">
                    <InputNumber min={0} style={{ width: "100%" }} />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name="compensation_amount" label="Компенсация, Br">
                    <InputNumber min={0} style={{ width: "100%" }} />
                  </Form.Item>
                </Col>
                <Col span={12}>
                  <Form.Item name="damage_amount" label="Ущерб, Br">
                    <InputNumber min={0} style={{ width: "100%" }} />
                  </Form.Item>
                </Col>
              </Row>
              <Form.Item name="comment" label="Комментарий">
                <Input.TextArea rows={2} />
              </Form.Item>
            </Form>
          </Space>
        ) : null}
      </Modal>
    </Space>
  );
}
