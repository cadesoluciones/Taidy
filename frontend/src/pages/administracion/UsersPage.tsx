import { PageHeader } from "../../components/PageHeader";
import { UserDirectory } from "../../components/UserDirectory";

export function UsersPage() {
  return (
    <section>
      <PageHeader title="Usuarios" />
      <UserDirectory />
    </section>
  );
}
