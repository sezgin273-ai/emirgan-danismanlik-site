<?php
declare(strict_types=1);

const ADMIN_SESSION_IDLE = 1800;
const ADMIN_MAX_ATTEMPTS = 5;
const ADMIN_LOCKOUT_SECONDS = 300;
const ADMIN_LOGIN_DELAY_SECONDS = 1;

function admin_config_path(): string
{
    return dirname(__DIR__) . '/config.php';
}

function admin_lockout_path(): string
{
    return dirname(__DIR__, 2) . '/content/.admin_lockout.json';
}

function load_admin_config(): array
{
    $path = admin_config_path();
    if (!is_readable($path)) {
        return [];
    }

    $config = require $path;

    return is_array($config) ? $config : [];
}

function admin_start_session(): void
{
    if (session_status() === PHP_SESSION_ACTIVE) {
        return;
    }

    session_set_cookie_params([
        'lifetime' => 0,
        'path' => '/',
        'httponly' => true,
        'samesite' => 'Lax',
        'secure' => !empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off',
    ]);
    session_name('emirgan_admin');
    session_start();
}

function admin_is_logged_in(): bool
{
    admin_start_session();

    if (empty($_SESSION['admin_authenticated'])) {
        return false;
    }

    $last = (int) ($_SESSION['admin_last_activity'] ?? 0);
    if ($last > 0 && (time() - $last) > ADMIN_SESSION_IDLE) {
        admin_logout();
        return false;
    }

    $_SESSION['admin_last_activity'] = time();

    return true;
}

function admin_require_login(): void
{
    if (!admin_is_logged_in()) {
        header('Location: /admin/login.php', true, 302);
        exit;
    }
}

function admin_logout(): void
{
    admin_start_session();
    $_SESSION = [];
    if (ini_get('session.use_cookies')) {
        $params = session_get_cookie_params();
        setcookie(session_name(), '', time() - 42000, $params['path'], $params['domain'] ?? '', (bool) $params['secure'], (bool) $params['httponly']);
    }
    session_destroy();
}

function admin_csrf_token(): string
{
    admin_start_session();
    if (empty($_SESSION['admin_csrf'])) {
        $_SESSION['admin_csrf'] = bin2hex(random_bytes(32));
    }

    return $_SESSION['admin_csrf'];
}

function admin_verify_csrf(?string $token): bool
{
    admin_start_session();
    if ($token === null || $token === '') {
        return false;
    }

    return hash_equals($_SESSION['admin_csrf'] ?? '', $token);
}

function admin_csrf_fail(): never
{
    http_response_code(403);
    echo 'Geçersiz güvenlik jetonu.';
    exit;
}

function admin_read_lockout(): array
{
    $path = admin_lockout_path();
    if (!is_readable($path)) {
        return ['attempts' => 0, 'locked_until' => 0];
    }

    $data = json_decode((string) file_get_contents($path), true);
    if (!is_array($data)) {
        return ['attempts' => 0, 'locked_until' => 0];
    }

    return [
        'attempts' => (int) ($data['attempts'] ?? 0),
        'locked_until' => (int) ($data['locked_until'] ?? 0),
    ];
}

function admin_write_lockout(array $data): void
{
    $path = admin_lockout_path();
    file_put_contents($path, json_encode($data, JSON_THROW_ON_ERROR), LOCK_EX);
}

function admin_is_locked_out(): bool
{
    $lock = admin_read_lockout();
    if ($lock['locked_until'] > time()) {
        return true;
    }

    if ($lock['locked_until'] > 0 && $lock['locked_until'] <= time()) {
        admin_write_lockout(['attempts' => 0, 'locked_until' => 0]);
    }

    return false;
}

function admin_record_failed_login(): void
{
    $lock = admin_read_lockout();
    $attempts = $lock['attempts'] + 1;
    $lockedUntil = 0;
    if ($attempts >= ADMIN_MAX_ATTEMPTS) {
        $lockedUntil = time() + ADMIN_LOCKOUT_SECONDS;
        $attempts = 0;
    }
    admin_write_lockout(['attempts' => $attempts, 'locked_until' => $lockedUntil]);
}

function admin_clear_lockout(): void
{
    admin_write_lockout(['attempts' => 0, 'locked_until' => 0]);
}

function admin_attempt_login(string $password): bool
{
    if (admin_is_locked_out()) {
        sleep(ADMIN_LOGIN_DELAY_SECONDS);
        return false;
    }

    $config = load_admin_config();
    $hash = $config['admin_password_hash'] ?? '';
    if ($hash === '' || !is_string($hash)) {
        sleep(ADMIN_LOGIN_DELAY_SECONDS);
        return false;
    }

    if (!password_verify($password, $hash)) {
        admin_record_failed_login();
        sleep(ADMIN_LOGIN_DELAY_SECONDS);
        return false;
    }

    admin_clear_lockout();
    admin_start_session();
    session_regenerate_id(true);
    $_SESSION['admin_authenticated'] = true;
    $_SESSION['admin_last_activity'] = time();
    $_SESSION['admin_csrf'] = bin2hex(random_bytes(32));

    return true;
}
