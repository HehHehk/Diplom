import { Layout, Menu, Space, Button, Dropdown, Avatar, Typography } from "antd";
import { Link, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";

const { Header, Content, Footer } = Layout;

export default function AppLayout() {
  const { user, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();

  const items = [
    { key: "/", label: <Link to="/">Каталог</Link> },
    ...(user ? [{ key: "/my", label: <Link to="/my">Мои брони</Link> }] : []),
    ...(user && (user.role === "owner" || user.role === "admin")
      ? [{ key: "/owner", label: <Link to="/owner">Кабинет арендодателя</Link> }]
      : []),
    ...(user?.role === "admin"
      ? [{ key: "/admin", label: <Link to="/admin">Админка</Link> }]
      : []),
  ];

  const selected =
    items.find((item) => item.key !== "/" && location.pathname.startsWith(item.key))?.key ??
    "/";

  return (
    <Layout className="app-shell">
      <Header className="app-header">
        <Link to="/" className="brand">
          <span className="brand-mark">А</span>
          <span>АрендаПро</span>
        </Link>
        <Menu mode="horizontal" selectedKeys={[selected]} items={items} className="app-menu" />
        <Space>
          {user ? (
            <Dropdown
              menu={{
                items: [
                  { key: "role", label: `Роль: ${user.role}`, disabled: true },
                  { key: "logout", label: "Выйти", onClick: () => { logout(); navigate("/"); } },
                ],
              }}
            >
              <Space className="user-chip">
                <Avatar size="small">{user.full_name?.[0] ?? user.email[0]}</Avatar>
                <Typography.Text>{user.full_name || user.email}</Typography.Text>
              </Space>
            </Dropdown>
          ) : (
            <>
              <Button onClick={() => navigate("/login")}>Войти</Button>
              <Button type="primary" onClick={() => navigate("/register")}>
                Регистрация
              </Button>
            </>
          )}
        </Space>
      </Header>
      <Content className="app-content">
        <Outlet />
      </Content>
      <Footer className="app-footer">
        Дипломный проект · аренда оборудования с интеллектуальным бронированием
      </Footer>
    </Layout>
  );
}
