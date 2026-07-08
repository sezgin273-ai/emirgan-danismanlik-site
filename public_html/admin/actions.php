<?php
declare(strict_types=1);

require_once __DIR__ . '/../includes/bootstrap.php';
require_once __DIR__ . '/../includes/admin_auth.php';
require_once __DIR__ . '/../includes/admin_multilang.php';
require_once __DIR__ . '/../includes/image_upload.php';

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    http_response_code(405);
    echo 'Method Not Allowed';
    exit;
}

if (!admin_verify_csrf($_POST['csrf_token'] ?? null)) {
    admin_csrf_fail();
}

admin_require_login();

$action = (string) ($_POST['action'] ?? '');
$redirect = '/admin/dashboard.php';
$flash = 'ok';

function admin_redirect(string $url, string $flash, string $message = ''): never
{
    admin_start_session();
    $_SESSION['admin_flash'] = ['type' => $flash, 'message' => $message];
    header('Location: ' . $url, true, 302);
    exit;
}

function admin_abort_with_status(int $statusCode, string $message): never
{
    http_response_code($statusCode);
    header('Content-Type: text/plain; charset=UTF-8');
    echo $message;
    exit;
}

function admin_text_length(string $text): int
{
    if (function_exists('mb_strlen')) {
        return mb_strlen($text, 'UTF-8');
    }

    return strlen($text);
}

function admin_normalize_content(array $posted, array $current, bool $structuralEdits = true): array
{
    $content = $current;

    if (isset($posted['site']) && is_array($posted['site'])) {
        $content['site']['title'] = trim((string) ($posted['site']['title'] ?? $content['site']['title']));
        if ($structuralEdits) {
            $content['site']['lang'] = trim((string) ($posted['site']['lang'] ?? $content['site']['lang']));
        }
        if (isset($posted['site']['meta']) && is_array($posted['site']['meta'])) {
            foreach (['description', 'og_title', 'og_description'] as $key) {
                $content['site']['meta'][$key] = trim((string) ($posted['site']['meta'][$key] ?? $content['site']['meta'][$key] ?? ''));
            }
        }
        if ($structuralEdits) {
            foreach ($content['site']['sections'] as $sid => $section) {
                $content['site']['sections'][$sid]['visible'] = !empty(
                    $posted['site']['sections'][$sid]['visible'] ?? null
                );
            }
        }
    }

    foreach (['hero', 'vision', 'mission', 'footer'] as $key) {
        if (!isset($posted[$key]) || !is_array($posted[$key])) {
            continue;
        }
        foreach ($posted[$key] as $field => $value) {
            if (is_string($value)) {
                $content[$key][$field] = trim($value);
            }
        }
    }

    if (isset($posted['hero']) && is_array($posted['hero'])) {
        if ($structuralEdits) {
            $content['hero']['watermark_enabled'] = !empty($posted['hero']['watermark_enabled']);
        }
    }

    if (isset($posted['intro']) && is_array($posted['intro'])) {
        $content['intro']['title'] = trim((string) ($posted['intro']['title'] ?? $content['intro']['title']));
        $content['intro']['text'] = trim((string) ($posted['intro']['text'] ?? $content['intro']['text']));
        if ($structuralEdits && isset($posted['intro']['badges_present'])) {
            $badges = [];
            if (isset($posted['intro']['badges']) && is_array($posted['intro']['badges'])) {
                foreach ($posted['intro']['badges'] as $badge) {
                    if (!is_array($badge)) {
                        continue;
                    }
                    $label = trim((string) ($badge['label'] ?? ''));
                    if ($label === '') {
                        continue;
                    }
                    $badges[] = [
                        'icon' => trim((string) ($badge['icon'] ?? 'energy')),
                        'label' => $label,
                    ];
                }
            }
            $content['intro']['badges'] = $badges;
        } elseif (!$structuralEdits && isset($posted['intro']['badges']) && is_array($posted['intro']['badges'])) {
            foreach ($posted['intro']['badges'] as $i => $badge) {
                if (!is_array($badge) || !isset($content['intro']['badges'][$i])) {
                    continue;
                }
                $label = trim((string) ($badge['label'] ?? ''));
                if ($label !== '') {
                    $content['intro']['badges'][$i]['label'] = $label;
                }
            }
        }
    }

    if (isset($posted['about']) && is_array($posted['about'])) {
        $content['about']['title'] = trim((string) ($posted['about']['title'] ?? $content['about']['title']));
        $content['about']['heading'] = trim((string) ($posted['about']['heading'] ?? $content['about']['heading']));
        if ($structuralEdits && isset($posted['about']['paragraphs_present'])) {
            $paragraphs = [];
            if (isset($posted['about']['paragraphs']) && is_array($posted['about']['paragraphs'])) {
                $paragraphs = array_values(array_filter(
                    array_map(static fn($p) => trim((string) $p), $posted['about']['paragraphs']),
                    static fn(string $p) => $p !== ''
                ));
            }
            $content['about']['paragraphs'] = $paragraphs;
        } elseif (!$structuralEdits && isset($posted['about']['paragraphs']) && is_array($posted['about']['paragraphs'])) {
            foreach ($posted['about']['paragraphs'] as $i => $paragraph) {
                if (isset($content['about']['paragraphs'][$i])) {
                    $content['about']['paragraphs'][$i] = trim((string) $paragraph);
                }
            }
        }
    }

    if (isset($posted['services']) && is_array($posted['services'])) {
        $content['services']['title'] = trim((string) ($posted['services']['title'] ?? $content['services']['title']));
        if ($structuralEdits && isset($posted['services']['items_present'])) {
            $items = [];
            if (isset($posted['services']['items']) && is_array($posted['services']['items'])) {
                foreach ($posted['services']['items'] as $item) {
                    if (!is_array($item)) {
                        continue;
                    }
                    $title = trim((string) ($item['title'] ?? ''));
                    if ($title === '') {
                        continue;
                    }
                    $icon = trim((string) ($item['icon'] ?? ''));
                    if ($icon === '') {
                        $icon = 'strategy';
                    }
                    if (!is_valid_service_icon($icon)) {
                        admin_abort_with_status(422, 'Geçersiz hizmet ikonu.');
                    }
                    $items[] = [
                        'title' => $title,
                        'description' => trim((string) ($item['description'] ?? '')),
                        'icon' => $icon,
                    ];
                }
            }
            $content['services']['items'] = $items;
        } elseif (!$structuralEdits && isset($posted['services']['items']) && is_array($posted['services']['items'])) {
            foreach ($posted['services']['items'] as $i => $item) {
                if (!is_array($item) || !isset($content['services']['items'][$i])) {
                    continue;
                }
                $title = trim((string) ($item['title'] ?? ''));
                if ($title !== '') {
                    $content['services']['items'][$i]['title'] = $title;
                }
                $content['services']['items'][$i]['description'] = trim((string) ($item['description'] ?? $content['services']['items'][$i]['description']));
            }
        }
    }

    if (isset($posted['process']) && is_array($posted['process'])) {
        if (!isset($content['process']) || !is_array($content['process'])) {
            $content['process'] = ['title' => '', 'steps' => []];
        }
        $content['process']['title'] = trim((string) ($posted['process']['title'] ?? $content['process']['title'] ?? ''));
        if ($structuralEdits && isset($posted['process']['steps_present'])) {
            $steps = [];
            if (isset($posted['process']['steps']) && is_array($posted['process']['steps'])) {
                foreach ($posted['process']['steps'] as $step) {
                    if (!is_array($step)) {
                        continue;
                    }
                    $title = trim((string) ($step['title'] ?? ''));
                    if ($title === '') {
                        continue;
                    }
                    $steps[] = [
                        'title' => $title,
                        'description' => trim((string) ($step['description'] ?? '')),
                    ];
                }
            }
            $content['process']['steps'] = $steps;
        } elseif (!$structuralEdits && isset($posted['process']['steps']) && is_array($posted['process']['steps'])) {
            foreach ($posted['process']['steps'] as $i => $step) {
                if (!is_array($step) || !isset($content['process']['steps'][$i])) {
                    continue;
                }
                $title = trim((string) ($step['title'] ?? ''));
                if ($title !== '') {
                    $content['process']['steps'][$i]['title'] = $title;
                }
                $content['process']['steps'][$i]['description'] = trim((string) ($step['description'] ?? $content['process']['steps'][$i]['description']));
            }
        }
    }

    if (isset($posted['team']) && is_array($posted['team'])) {
        $content['team']['title'] = trim((string) ($posted['team']['title'] ?? $content['team']['title']));
        $content['team']['intro'] = trim((string) ($posted['team']['intro'] ?? $content['team']['intro']));
        if ($structuralEdits && isset($posted['team']['members_present'])) {
            $members = [];
            if (isset($posted['team']['members']) && is_array($posted['team']['members'])) {
                foreach ($posted['team']['members'] as $idx => $member) {
                    if (!is_array($member)) {
                        continue;
                    }
                    $name = trim((string) ($member['name'] ?? ''));
                    if ($name === '') {
                        continue;
                    }
                    $photo = trim((string) ($member['photo'] ?? ''));
                    $members[] = [
                        'name' => $name,
                        'title' => trim((string) ($member['title'] ?? '')),
                        'description' => trim((string) ($member['description'] ?? '')),
                        'photo' => $photo,
                    ];
                }
            }
            $content['team']['members'] = $members;
        } elseif (!$structuralEdits && isset($posted['team']['members']) && is_array($posted['team']['members'])) {
            foreach ($posted['team']['members'] as $i => $member) {
                if (!is_array($member) || !isset($content['team']['members'][$i])) {
                    continue;
                }
                $name = trim((string) ($member['name'] ?? ''));
                if ($name !== '') {
                    $content['team']['members'][$i]['name'] = $name;
                }
                $content['team']['members'][$i]['title'] = trim((string) ($member['title'] ?? $content['team']['members'][$i]['title']));
                $content['team']['members'][$i]['description'] = trim((string) ($member['description'] ?? $content['team']['members'][$i]['description']));
            }
        }
    }

    if ($structuralEdits && isset($posted['display']) && is_array($posted['display'])) {
        if (!isset($content['display']) || !is_array($content['display'])) {
            $content['display'] = [];
        }
        foreach (display_size_groups() as $group) {
            if (!array_key_exists($group, $posted['display'])) {
                continue;
            }
            $size = trim((string) $posted['display'][$group]);
            if (!is_valid_display_size($size)) {
                admin_abort_with_status(422, 'Geçersiz görsel boyutu.');
            }
            $content['display'][$group] = $size;
        }
    }

    if (isset($posted['contact']) && is_array($posted['contact'])) {
        $content['contact']['title'] = trim((string) ($posted['contact']['title'] ?? $content['contact']['title']));
        $content['contact']['heading'] = trim((string) ($posted['contact']['heading'] ?? $content['contact']['heading']));
        $content['contact']['email'] = trim((string) ($posted['contact']['email'] ?? $content['contact']['email']));
        if ($structuralEdits && isset($posted['contact']['info_items_present'])) {
            $infoItems = [];
            if (isset($posted['contact']['info_items']) && is_array($posted['contact']['info_items'])) {
                foreach ($posted['contact']['info_items'] as $item) {
                    if (!is_array($item)) {
                        continue;
                    }
                    $type = trim((string) ($item['type'] ?? ''));
                    if (!is_valid_contact_info_type($type)) {
                        admin_abort_with_status(422, 'Geçersiz iletişim bilgisi tipi.');
                    }
                    $title = str_replace(["\r", "\n", "\0"], '', trim((string) ($item['title'] ?? '')));
                    $value = str_replace(["\r", "\n", "\0"], '', trim((string) ($item['value'] ?? '')));
                    if ($title === '' || $value === '') {
                        continue;
                    }
                    if (admin_text_length($title) > 80 || admin_text_length($value) > 500) {
                        admin_abort_with_status(422, 'İletişim bilgisi alanı çok uzun.');
                    }
                    $infoItems[] = [
                        'type' => $type,
                        'title' => $title,
                        'value' => $value,
                    ];
                }
            }
            $content['contact']['info_items'] = $infoItems;
        } elseif (!$structuralEdits && isset($posted['contact']['info_items']) && is_array($posted['contact']['info_items'])) {
            foreach ($posted['contact']['info_items'] as $i => $item) {
                if (!is_array($item) || !isset($content['contact']['info_items'][$i])) {
                    continue;
                }
                $title = trim((string) ($item['title'] ?? ''));
                if ($title !== '') {
                    $content['contact']['info_items'][$i]['title'] = $title;
                }
            }
        }
        if ($structuralEdits && isset($posted['contact']['addresses_present'])) {
            $addresses = [];
            if (isset($posted['contact']['addresses']) && is_array($posted['contact']['addresses'])) {
                foreach ($posted['contact']['addresses'] as $addr) {
                    if (!is_array($addr)) {
                        continue;
                    }
                    $label = trim((string) ($addr['label'] ?? ''));
                    if ($label === '') {
                        continue;
                    }
                    $addresses[] = [
                        'label' => $label,
                        'text' => trim((string) ($addr['text'] ?? '')),
                    ];
                }
            }
            $content['contact']['addresses'] = $addresses;
        } elseif (!$structuralEdits && isset($posted['contact']['addresses']) && is_array($posted['contact']['addresses'])) {
            foreach ($posted['contact']['addresses'] as $i => $addr) {
                if (!is_array($addr) || !isset($content['contact']['addresses'][$i])) {
                    continue;
                }
                $label = trim((string) ($addr['label'] ?? ''));
                if ($label !== '') {
                    $content['contact']['addresses'][$i]['label'] = $label;
                }
            }
        }
        if (isset($posted['contact']['form']) && is_array($posted['contact']['form'])) {
            foreach ($posted['contact']['form'] as $field => $value) {
                if ($field === 'submit' || $field === 'success' || $field === 'error') {
                    $content['contact']['form'][$field] = trim((string) $value);
                } elseif (is_array($value)) {
                    $content['contact']['form'][$field] = [
                        'label' => trim((string) ($value['label'] ?? '')),
                        'placeholder' => trim((string) ($value['placeholder'] ?? '')),
                    ];
                }
            }
        }
        if ($structuralEdits && isset($posted['contact']['hours_present'])) {
            $hoursTitle = str_replace(["\r", "\n", "\0"], '', trim((string) ($posted['contact']['hours']['title'] ?? '')));
            $hoursRows = [];
            if (isset($posted['contact']['hours']['rows']) && is_array($posted['contact']['hours']['rows'])) {
                foreach ($posted['contact']['hours']['rows'] as $row) {
                    if (!is_array($row)) {
                        continue;
                    }
                    $label = str_replace(["\r", "\n", "\0"], '', trim((string) ($row['label'] ?? '')));
                    $value = str_replace(["\r", "\n", "\0"], '', trim((string) ($row['value'] ?? '')));
                    if ($label === '' || $value === '') {
                        continue;
                    }
                    if (admin_text_length($label) > 80 || admin_text_length($value) > 80) {
                        admin_abort_with_status(422, 'Çalışma saatleri alanı çok uzun.');
                    }
                    $hoursRows[] = [
                        'label' => $label,
                        'value' => $value,
                    ];
                }
            }
            if ($hoursTitle === '' || count($hoursRows) === 0) {
                unset($content['contact']['hours']);
            } else {
                if (admin_text_length($hoursTitle) > 80) {
                    admin_abort_with_status(422, 'Çalışma saatleri başlığı çok uzun.');
                }
                $content['contact']['hours'] = [
                    'title' => $hoursTitle,
                    'rows' => $hoursRows,
                ];
            }
        } elseif (!$structuralEdits && isset($posted['contact']['hours']) && is_array($posted['contact']['hours'])) {
            if (isset($content['contact']['hours']) && is_array($content['contact']['hours'])) {
                $hoursTitle = str_replace(["\r", "\n", "\0"], '', trim((string) ($posted['contact']['hours']['title'] ?? '')));
                if ($hoursTitle !== '') {
                    $content['contact']['hours']['title'] = $hoursTitle;
                }
                if (isset($posted['contact']['hours']['rows']) && is_array($posted['contact']['hours']['rows'])) {
                    foreach ($posted['contact']['hours']['rows'] as $i => $row) {
                        if (!is_array($row) || !isset($content['contact']['hours']['rows'][$i])) {
                            continue;
                        }
                        $label = str_replace(["\r", "\n", "\0"], '', trim((string) ($row['label'] ?? '')));
                        if ($label !== '') {
                            $content['contact']['hours']['rows'][$i]['label'] = $label;
                        }
                    }
                }
            }
        }
    }

    if (isset($posted['navigation']) && is_array($posted['navigation'])) {
        if (isset($posted['navigation']['items']) && is_array($posted['navigation']['items'])) {
            foreach ($posted['navigation']['items'] as $idx => $item) {
                if (!is_array($item)) {
                    continue;
                }
                if (isset($content['navigation']['items'][$idx])) {
                    $content['navigation']['items'][$idx]['label'] = trim((string) ($item['label'] ?? $content['navigation']['items'][$idx]['label']));
                }
            }
        }
        if (isset($posted['navigation']['cta']) && is_array($posted['navigation']['cta'])) {
            $content['navigation']['cta']['label'] = trim((string) ($posted['navigation']['cta']['label'] ?? $content['navigation']['cta']['label']));
        }
    }

    if (isset($posted['ui']) && is_array($posted['ui'])) {
        foreach ($posted['ui'] as $key => $value) {
            if (is_string($value)) {
                $content['ui'][$key] = trim($value);
            }
        }
    }

    if (isset($posted['kvkk']) && is_array($posted['kvkk'])) {
        $content['kvkk']['title'] = trim((string) ($posted['kvkk']['title'] ?? $content['kvkk']['title']));
        $content['kvkk']['intro'] = trim((string) ($posted['kvkk']['intro'] ?? $content['kvkk']['intro']));
        $content['kvkk']['note'] = trim((string) ($posted['kvkk']['note'] ?? $content['kvkk']['note'] ?? ''));
        if ($structuralEdits && isset($posted['kvkk']['sections_present'])) {
            $sections = [];
            if (isset($posted['kvkk']['sections']) && is_array($posted['kvkk']['sections'])) {
                foreach ($posted['kvkk']['sections'] as $section) {
                    if (!is_array($section)) {
                        continue;
                    }
                    $heading = trim((string) ($section['heading'] ?? ''));
                    if ($heading === '') {
                        continue;
                    }
                    $paragraphs = [];
                    if (isset($section['paragraphs']) && is_array($section['paragraphs'])) {
                        $paragraphs = array_values(array_filter(
                            array_map(static fn($p) => trim((string) $p), $section['paragraphs']),
                            static fn(string $p) => $p !== ''
                        ));
                    }
                    $sections[] = ['heading' => $heading, 'paragraphs' => $paragraphs];
                }
            }
            $content['kvkk']['sections'] = $sections;
        } elseif (!$structuralEdits && isset($posted['kvkk']['sections']) && is_array($posted['kvkk']['sections'])) {
            foreach ($posted['kvkk']['sections'] as $i => $section) {
                if (!is_array($section) || !isset($content['kvkk']['sections'][$i])) {
                    continue;
                }
                $heading = trim((string) ($section['heading'] ?? ''));
                if ($heading !== '') {
                    $content['kvkk']['sections'][$i]['heading'] = $heading;
                }
                if (isset($section['paragraphs']) && is_array($section['paragraphs'])) {
                    foreach ($section['paragraphs'] as $j => $paragraph) {
                        if (isset($content['kvkk']['sections'][$i]['paragraphs'][$j])) {
                            $content['kvkk']['sections'][$i]['paragraphs'][$j] = trim((string) $paragraph);
                        }
                    }
                }
            }
        }
    }

    return $content;
}

$current = load_content();

match ($action) {
    'logout' => (function () {
        admin_logout();
        admin_redirect('/admin/login.php', 'ok', 'Oturum kapatıldı.');
    })(),
    'save_content' => (function () {
        $lang = admin_resolve_lang_from_post();
        $current = admin_load_lang_file($lang);
        $posted = $_POST['content'] ?? null;
        if (!is_array($posted)) {
            admin_redirect(admin_dashboard_url($lang), 'error', 'Geçersiz içerik verisi.');
        }
        $structural = admin_is_tr_mode($lang);
        $merged = admin_normalize_content($posted, $current, $structural);
        $saved = $structural
            ? admin_save_tr_with_structure_sync($merged)
            : admin_save_localized_text($lang, $merged);
        if (!$saved) {
            admin_redirect(admin_dashboard_url($lang), 'error', 'İçerik kaydedilemedi.');
        }
        admin_redirect(admin_dashboard_url($lang), 'ok', 'İçerik kaydedildi.');
    })(),
    'upload_team_photo' => (function () use ($current) {
        admin_require_tr_mode(admin_resolve_lang_from_post());
        $index = (int) ($_POST['member_index'] ?? -1);
        if ($index < 0 || !isset($current['team']['members'][$index])) {
            admin_redirect('/admin/dashboard.php#team', 'error', 'Geçersiz ekip üyesi.');
        }
        $file = $_FILES['photo'] ?? null;
        if (!is_array($file)) {
            admin_redirect('/admin/dashboard.php#team', 'error', 'Dosya seçilmedi.');
        }
        $result = save_uploaded_team_photo($file);
        if (!$result['ok']) {
            admin_redirect('/admin/dashboard.php#team', 'error', $result['error']);
        }
        delete_uploaded_file($current['team']['members'][$index]['photo'] ?? '');
        $current['team']['members'][$index]['photo'] = $result['path'];
        if (!admin_save_tr_lang_independent_sync($current)) {
            admin_redirect('/admin/dashboard.php#team', 'error', 'Fotoğraf yolu kaydedilemedi.');
        }
        admin_redirect('/admin/dashboard.php#team', 'ok', 'Ekip fotoğrafı yüklendi.');
    })(),
    'remove_team_photo' => (function () use ($current) {
        admin_require_tr_mode(admin_resolve_lang_from_post());
        $rawIndex = $_POST['member_index'] ?? null;
        $index = filter_var($rawIndex, FILTER_VALIDATE_INT, ['options' => ['min_range' => 0]]);
        if ($index === false || !isset($current['team']['members'][$index])) {
            admin_abort_with_status(422, 'Geçersiz ekip üyesi index değeri.');
        }

        $postedName = str_replace(["\r", "\n", "\0"], '', trim((string) ($_POST['member_name'] ?? '')));
        $serverName = trim((string) ($current['team']['members'][$index]['name'] ?? ''));
        if ($postedName === '' || $postedName !== $serverName) {
            admin_abort_with_status(409, 'Ekip üyesi sırası değişmiş olabilir. Önce kaydedin veya sayfayı yenileyin.');
        }

        $photoPath = trim((string) ($current['team']['members'][$index]['photo'] ?? ''));
        $current['team']['members'][$index]['photo'] = '';

        $canDeletePhoto = $photoPath !== '' && str_starts_with($photoPath, uploads_url_prefix() . '/');
        if ($canDeletePhoto) {
            foreach ($current['team']['members'] as $member) {
                if (($member['photo'] ?? '') === $photoPath) {
                    $canDeletePhoto = false;
                    break;
                }
            }
        }

        if (!admin_save_tr_lang_independent_sync($current)) {
            admin_redirect('/admin/dashboard.php#team', 'error', 'Fotoğraf kaldırılamadı.');
        }

        if ($canDeletePhoto) {
            delete_uploaded_file($photoPath);
        }
        admin_redirect('/admin/dashboard.php#team', 'ok', 'Fotoğraf kaldırıldı.');
    })(),
    'delete_team_member' => (function () use ($current) {
        admin_require_tr_mode(admin_resolve_lang_from_post());
        $rawIndex = $_POST['member_index'] ?? null;
        $index = filter_var($rawIndex, FILTER_VALIDATE_INT, ['options' => ['min_range' => 0]]);
        if ($index === false || !isset($current['team']['members'][$index])) {
            admin_abort_with_status(422, 'Geçersiz ekip üyesi index değeri.');
        }

        $postedName = str_replace(["\r", "\n", "\0"], '', trim((string) ($_POST['member_name'] ?? '')));
        $serverName = trim((string) ($current['team']['members'][$index]['name'] ?? ''));
        if ($postedName === '' || $postedName !== $serverName) {
            admin_abort_with_status(409, 'Ekip üyesi sırası değişmiş olabilir. Önce kaydedin veya sayfayı yenileyin.');
        }

        $members = $current['team']['members'];
        $removed = $members[$index];
        unset($members[$index]);
        $current['team']['members'] = array_values($members);

        $removedPhoto = trim((string) ($removed['photo'] ?? ''));
        $canDeletePhoto = $removedPhoto !== '' && str_starts_with($removedPhoto, uploads_url_prefix() . '/');
        if ($canDeletePhoto) {
            foreach ($current['team']['members'] as $member) {
                if (($member['photo'] ?? '') === $removedPhoto) {
                    $canDeletePhoto = false;
                    break;
                }
            }
        }

        if (!admin_save_tr_with_structure_sync($current)) {
            admin_redirect('/admin/dashboard.php#team', 'error', 'Ekip üyesi silinemedi.');
        }

        if ($canDeletePhoto) {
            delete_uploaded_file($removedPhoto);
        }
        admin_redirect('/admin/dashboard.php#team', 'ok', 'Ekip üyesi silindi.');
    })(),
    'delete_process_step' => (function () use ($current) {
        admin_require_tr_mode(admin_resolve_lang_from_post());
        $rawIndex = $_POST['step_index'] ?? null;
        $index = filter_var($rawIndex, FILTER_VALIDATE_INT, ['options' => ['min_range' => 0]]);
        $steps = $current['process']['steps'] ?? [];
        if ($index === false || !isset($steps[$index])) {
            admin_abort_with_status(422, 'Geçersiz süreç adımı index değeri.');
        }

        $postedTitle = str_replace(["\r", "\n", "\0"], '', trim((string) ($_POST['step_title'] ?? '')));
        $serverTitle = trim((string) ($steps[$index]['title'] ?? ''));
        if ($postedTitle === '' || $postedTitle !== $serverTitle) {
            admin_abort_with_status(409, 'Süreç adımı sırası değişmiş olabilir. Önce kaydedin veya sayfayı yenileyin.');
        }

        unset($steps[$index]);
        $current['process']['steps'] = array_values($steps);

        if (!admin_save_tr_with_structure_sync($current)) {
            admin_redirect('/admin/dashboard.php#process', 'error', 'Süreç adımı silinemedi.');
        }
        admin_redirect('/admin/dashboard.php#process', 'ok', 'Süreç adımı silindi.');
    })(),
    'upload_asset' => (function () use ($current) {
        admin_require_tr_mode(admin_resolve_lang_from_post());
        $assetKey = (string) ($_POST['asset_key'] ?? '');
        $allowed = ['logo_light', 'logo_dark', 'emblem', 'favicon', 'apple_touch_icon'];
        if (!in_array($assetKey, $allowed, true)) {
            admin_redirect('/admin/dashboard.php#media', 'error', 'Geçersiz varlık türü.');
        }
        $file = $_FILES['asset_file'] ?? null;
        if (!is_array($file)) {
            admin_redirect('/admin/dashboard.php#media', 'error', 'Dosya seçilmedi.');
        }
        $prefix = str_replace('_', '-', $assetKey);
        $result = save_uploaded_brand_image($file, $prefix);
        if (!$result['ok']) {
            admin_redirect('/admin/dashboard.php#media', 'error', $result['error']);
        }
        $jsonKey = $assetKey === 'logo_light' ? 'logo_light' : ($assetKey === 'logo_dark' ? 'logo_dark' : $assetKey);
        if ($assetKey === 'apple_touch_icon') {
            $jsonKey = 'apple_touch_icon';
        }
        $current['site']['assets'][$jsonKey] = $result['path'];
        if (!admin_save_tr_lang_independent_sync($current)) {
            admin_redirect('/admin/dashboard.php#media', 'error', 'Varlık yolu kaydedilemedi.');
        }
        admin_redirect('/admin/dashboard.php#media', 'ok', 'Görsel yüklendi (yeni dosya yolu kaydedildi).');
    })(),
    'restore_backup' => (function () {
        $lang = admin_resolve_lang_from_post();
        $name = (string) ($_POST['backup_name'] ?? '');
        if (!restore_content_backup($name, $lang)) {
            admin_redirect(admin_dashboard_url($lang, 'backups'), 'error', 'Yedek geri yüklenemedi.');
        }
        admin_redirect(admin_dashboard_url($lang), 'ok', 'Yedek geri yüklendi.');
    })(),
    'delete_backup' => (function () {
        $lang = admin_resolve_lang_from_post();
        $name = (string) ($_POST['backup_name'] ?? '');
        if (!is_valid_backup_name($name, $lang)) {
            admin_abort_with_status(422, 'Geçersiz yedek dosya adı.');
        }
        if (!delete_content_backup($name, $lang)) {
            admin_redirect(admin_dashboard_url($lang, 'backups'), 'error', 'Yedek silinemedi.');
        }
        admin_redirect(admin_dashboard_url($lang, 'backups'), 'ok', 'Yedek silindi.');
    })(),
    'label_backup' => (function () {
        $lang = admin_resolve_lang_from_post();
        $name = (string) ($_POST['backup_name'] ?? '');
        if (!is_valid_backup_name($name, $lang)) {
            admin_abort_with_status(422, 'Geçersiz yedek dosya adı.');
        }
        $label = (string) ($_POST['backup_label'] ?? '');
        if (!set_backup_label($name, $label, $lang)) {
            admin_abort_with_status(422, 'Geçersiz yedek etiketi.');
        }
        admin_redirect(admin_dashboard_url($lang, 'backups'), 'ok', 'Yedek etiketi kaydedildi.');
    })(),
    'delete_contact_info_item' => (function () use ($current) {
        admin_require_tr_mode(admin_resolve_lang_from_post());
        $rawIndex = $_POST['info_index'] ?? null;
        $index = filter_var($rawIndex, FILTER_VALIDATE_INT, ['options' => ['min_range' => 0]]);
        $items = $current['contact']['info_items'] ?? [];
        if ($index === false || !isset($items[$index])) {
            admin_abort_with_status(422, 'Geçersiz iletişim bilgisi index değeri.');
        }

        $postedTitle = str_replace(["\r", "\n", "\0"], '', trim((string) ($_POST['info_title'] ?? '')));
        $serverTitle = trim((string) ($items[$index]['title'] ?? ''));
        if ($postedTitle === '' || $postedTitle !== $serverTitle) {
            admin_abort_with_status(409, 'İletişim bilgisi sırası değişmiş olabilir. Önce kaydedin veya sayfayı yenileyin.');
        }

        unset($items[$index]);
        $current['contact']['info_items'] = array_values($items);

        if (!admin_save_tr_with_structure_sync($current)) {
            admin_redirect('/admin/dashboard.php#contact', 'error', 'İletişim bilgisi silinemedi.');
        }
        admin_redirect('/admin/dashboard.php#contact', 'ok', 'İletişim bilgisi silindi.');
    })(),
    'delete_contact_hours_row' => (function () use ($current) {
        admin_require_tr_mode(admin_resolve_lang_from_post());
        $rawIndex = $_POST['hours_index'] ?? null;
        $index = filter_var($rawIndex, FILTER_VALIDATE_INT, ['options' => ['min_range' => 0]]);
        $hours = $current['contact']['hours'] ?? [];
        $rows = is_array($hours['rows'] ?? null) ? $hours['rows'] : [];
        if ($index === false || !isset($rows[$index])) {
            admin_abort_with_status(422, 'Geçersiz çalışma saatleri index değeri.');
        }

        $postedLabel = str_replace(["\r", "\n", "\0"], '', trim((string) ($_POST['hours_label'] ?? '')));
        $serverLabel = trim((string) ($rows[$index]['label'] ?? ''));
        if ($postedLabel === '' || $postedLabel !== $serverLabel) {
            admin_abort_with_status(409, 'Çalışma saatleri sırası değişmiş olabilir. Önce kaydedin veya sayfayı yenileyin.');
        }

        unset($rows[$index]);
        $rows = array_values($rows);
        $title = trim((string) ($hours['title'] ?? ''));
        if ($title === '' || count($rows) === 0) {
            unset($current['contact']['hours']);
        } else {
            $current['contact']['hours']['rows'] = $rows;
        }

        if (!admin_save_tr_with_structure_sync($current)) {
            admin_redirect('/admin/dashboard.php#contact', 'error', 'Çalışma saati satırı silinemedi.');
        }
        admin_redirect('/admin/dashboard.php#contact', 'ok', 'Çalışma saati satırı silindi.');
    })(),
    default => admin_redirect('/admin/dashboard.php', 'error', 'Bilinmeyen işlem.'),
};
