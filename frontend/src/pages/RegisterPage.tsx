import { App, Button, Card, Form, Input, Radio, Typography } from "antd";
import { Link, useNavigate } from "react-router-dom";
import { apiError } from "../api/client";
import { useAuth } from "../auth";

export default function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const { message } = App.useApp();

  const onFinish = async (values: {
    email: string;
    password: string;
    full_name: string;
    role: "user" | "owner";
  }) => {
    try {
      const debugToken = await register(values);
      if (debugToken) {
        message.info("Подтвердите email, чтобы войти");
        navigate(`/verify?token=${encodeURIComponent(debugToken)}`);
      } else {
        message.success("Письмо с подтверждением отправлено на почту");
        navigate("/login");
      }
    } catch (error) {
      message.error(apiError(error));
    }
  };

  return (
    <div className="auth-wrap">
      <Card className="auth-card">
        <Typography.Title level={3}>Регистрация</Typography.Title>
        <Form
          layout="vertical"
          initialValues={{ role: "user" }}
          onFinish={onFinish}
        >
          <Form.Item name="full_name" label="Имя" rules={[{ required: true }]}>
            <Input />
          </Form.Item>
          <Form.Item
            name="email"
            label="Email"
            rules={[{ required: true, type: "email" }]}
          >
            <Input autoComplete="username" />
          </Form.Item>
          <Form.Item
            name="password"
            label="Пароль"
            rules={[{ required: true, min: 6 }]}
          >
            <Input.Password autoComplete="new-password" />
          </Form.Item>
          <Form.Item name="role" label="Я хочу">
            <Radio.Group>
              <Radio.Button value="user">Арендовать</Radio.Button>
              <Radio.Button value="owner">Сдавать оборудование</Radio.Button>
            </Radio.Group>
          </Form.Item>
          <Button type="primary" htmlType="submit" block>
            Создать аккаунт
          </Button>
        </Form>
        <Typography.Paragraph style={{ marginTop: 16, marginBottom: 0 }}>
          Уже есть аккаунт? <Link to="/login">Войти</Link>
        </Typography.Paragraph>
      </Card>
    </div>
  );
}
