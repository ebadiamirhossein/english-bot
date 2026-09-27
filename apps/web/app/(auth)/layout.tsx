/**
 * The shell for sign-in and enrolment: no bottom nav, one centred column.
 *
 * Same palette, same type, same `max-w-lg` phone width as the app shell. These
 * are the first two screens either learner ever sees, and a sign-in page that
 * looks like a different product is how an app stops feeling like one thing.
 */
export default function AuthLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <div className="mx-auto flex min-h-dvh w-full max-w-lg flex-col justify-center lg:max-w-2xl px-5 py-12">
      <main className="space-y-8">{children}</main>
    </div>
  );
}
