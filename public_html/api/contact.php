<?php
declare(strict_types=1);

require_once dirname(__DIR__) . '/includes/bootstrap.php';

if (session_status() !== PHP_SESSION_ACTIVE) {
    session_set_cookie_params([
        'lifetime' => 0,
        'path' => '/',
        'httponly' => true,
        'samesite' => 'Lax',
        'secure' => !empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off',
    ]);
    session_start();
}

function contact_encode_mime_header(string $text): string
{
    if (function_exists('mb_encode_mimeheader')) {
        return mb_encode_mimeheader($text, 'UTF-8', 'B', "\r\n");
    }

    return '=?UTF-8?B?' . base64_encode($text) . '?=';
}

function contact_strip_crlf(string $value): string
{
    return str_replace(["\r", "\n", "\0"], '', $value);
}

function contact_wants_json(): bool
{
    $accept = strtolower((string) ($_SERVER['HTTP_ACCEPT'] ?? ''));
    if (str_contains($accept, 'application/json')) {
        return true;
    }

    $requestedWith = strtolower((string) ($_SERVER['HTTP_X_REQUESTED_WITH'] ?? ''));

    return $requestedWith === 'xmlhttprequest';
}

function contact_respond(bool $ok, string $message, int $status = 200): void
{
    if (contact_wants_json()) {
        http_response_code($status);
        header('Content-Type: application/json; charset=utf-8');
        echo json_encode(['ok' => $ok, 'message' => $message], JSON_UNESCAPED_UNICODE);
        exit;
    }

    $_SESSION['contact_flash'] = ['ok' => $ok, 'message' => $message];
    header('Location: /#contact', true, 303);
    exit;
}

function contact_load_config(): array
{
    $path = dirname(__DIR__) . '/config.php';
    if (!is_readable($path)) {
        return [];
    }

    $config = require $path;

    return is_array($config) ? $config : [];
}

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    if (contact_wants_json()) {
        http_response_code(405);
        header('Content-Type: application/json; charset=utf-8');
        echo json_encode(['ok' => false, 'error' => 'Yalnızca POST istekleri kabul edilir.'], JSON_UNESCAPED_UNICODE);
        exit;
    }

    http_response_code(405);
    echo 'Yalnızca POST istekleri kabul edilir.';
    exit;
}

$content = load_content();
$successMessage = (string) ($content['contact']['form']['success'] ?? 'Mesajınız alındı.');
$errorMessage = (string) ($content['contact']['form']['error'] ?? 'Lütfen formu kontrol edin.');

$honeypot = contact_strip_crlf(trim((string) ($_POST['website'] ?? '')));
if ($honeypot !== '') {
    contact_respond(true, $successMessage, 200);
}

$now = time();
$lastSent = (int) ($_SESSION['contact_last_sent'] ?? 0);
if ($lastSent > 0 && ($now - $lastSent) < 60) {
    if (contact_wants_json()) {
        http_response_code(429);
        header('Content-Type: application/json; charset=utf-8');
        echo json_encode(['ok' => false, 'message' => $errorMessage], JSON_UNESCAPED_UNICODE);
        exit;
    }

    $_SESSION['contact_flash'] = ['ok' => false, 'message' => $errorMessage];
    header('Location: /#contact', true, 429);
    exit;
}

$name = contact_strip_crlf(trim((string) ($_POST['name'] ?? '')));
$email = contact_strip_crlf(trim((string) ($_POST['email'] ?? '')));
$phone = contact_strip_crlf(trim((string) ($_POST['phone'] ?? '')));
$subject = contact_strip_crlf(trim((string) ($_POST['subject'] ?? '')));
$message = trim((string) ($_POST['message'] ?? ''));
$message = str_replace(["\r\n", "\r"], "\n", $message);

if ($name === '' || $email === '' || $message === '') {
    if (contact_wants_json()) {
        http_response_code(422);
        header('Content-Type: application/json; charset=utf-8');
        echo json_encode(['ok' => false, 'message' => $errorMessage], JSON_UNESCAPED_UNICODE);
        exit;
    }

    $_SESSION['contact_flash'] = ['ok' => false, 'message' => $errorMessage];
    header('Location: /#contact', true, 303);
    exit;
}

if (!filter_var($email, FILTER_VALIDATE_EMAIL)) {
    if (contact_wants_json()) {
        http_response_code(422);
        header('Content-Type: application/json; charset=utf-8');
        echo json_encode(['ok' => false, 'message' => $errorMessage], JSON_UNESCAPED_UNICODE);
        exit;
    }

    $_SESSION['contact_flash'] = ['ok' => false, 'message' => $errorMessage];
    header('Location: /#contact', true, 303);
    exit;
}

$limits = [
    'name' => 100,
    'email' => 150,
    'phone' => 30,
    'subject' => 150,
    'message' => 5000,
];

if (
    strlen($name) > $limits['name']
    || strlen($email) > $limits['email']
    || strlen($phone) > $limits['phone']
    || strlen($subject) > $limits['subject']
    || strlen($message) > $limits['message']
) {
    if (contact_wants_json()) {
        http_response_code(422);
        header('Content-Type: application/json; charset=utf-8');
        echo json_encode(['ok' => false, 'message' => $errorMessage], JSON_UNESCAPED_UNICODE);
        exit;
    }

    $_SESSION['contact_flash'] = ['ok' => false, 'message' => $errorMessage];
    header('Location: /#contact', true, 303);
    exit;
}

$config = contact_load_config();
$mailMode = (string) ($config['mail_mode'] ?? 'log');
$defaultMailTo = 'info@emirgandanismanlik.com';
$rawMailTo = contact_strip_crlf(trim((string) ($config['mail_to'] ?? $defaultMailTo)));
$mailTo = ($rawMailTo !== '' && filter_var($rawMailTo, FILTER_VALIDATE_EMAIL))
    ? $rawMailTo
    : $defaultMailTo;

$payload = [
    'timestamp' => date('c'),
    'name' => $name,
    'email' => $email,
    'phone' => $phone,
    'subject' => $subject,
    'message' => $message,
    'ip' => contact_strip_crlf((string) ($_SERVER['REMOTE_ADDR'] ?? '')),
];

if ($mailMode === 'mail') {
    $encodedSubject = $subject !== '' ? $subject : 'İletişim formu mesajı';
    $mimeSubject = contact_encode_mime_header($encodedSubject);
    $body = "Ad Soyad: {$name}\n"
        . "E-posta: {$email}\n"
        . "Telefon: {$phone}\n"
        . "Konu: {$subject}\n\n"
        . $message;

    $headers = [
        'MIME-Version: 1.0',
        'Content-Type: text/plain; charset=UTF-8',
        'From: ' . contact_encode_mime_header('Emirgan Danışmanlık') . ' <' . $mailTo . '>',
        'Reply-To: ' . $email,
    ];

    $sent = @mail($mailTo, $mimeSubject, $body, implode("\r\n", $headers), '-f' . $mailTo);
    if (!$sent) {
        if (contact_wants_json()) {
            http_response_code(500);
            header('Content-Type: application/json; charset=utf-8');
            echo json_encode(['ok' => false, 'message' => $errorMessage], JSON_UNESCAPED_UNICODE);
            exit;
        }

        $_SESSION['contact_flash'] = ['ok' => false, 'message' => $errorMessage];
        header('Location: /#contact', true, 303);
        exit;
    }
} else {
    $logDir = dirname(__DIR__, 2) . '/content/mail-log';
    if (!is_dir($logDir) && !mkdir($logDir, 0755, true) && !is_dir($logDir)) {
        if (contact_wants_json()) {
            http_response_code(500);
            header('Content-Type: application/json; charset=utf-8');
            echo json_encode(['ok' => false, 'message' => $errorMessage], JSON_UNESCAPED_UNICODE);
            exit;
        }

        $_SESSION['contact_flash'] = ['ok' => false, 'message' => $errorMessage];
        header('Location: /#contact', true, 303);
        exit;
    }

    $filename = date('Ymd-His') . '-' . bin2hex(random_bytes(4)) . '.json';
    $written = file_put_contents(
        $logDir . '/' . $filename,
        json_encode($payload, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE) . "\n",
        LOCK_EX
    );

    if ($written === false) {
        if (contact_wants_json()) {
            http_response_code(500);
            header('Content-Type: application/json; charset=utf-8');
            echo json_encode(['ok' => false, 'message' => $errorMessage], JSON_UNESCAPED_UNICODE);
            exit;
        }

        $_SESSION['contact_flash'] = ['ok' => false, 'message' => $errorMessage];
        header('Location: /#contact', true, 303);
        exit;
    }
}

$_SESSION['contact_last_sent'] = $now;
contact_respond(true, $successMessage, 200);
