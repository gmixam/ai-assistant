# AI Assistant Platform Architecture

## Overview

AI Assistant Platform --- это система для автоматического выполнения
задач с помощью AI.

Пользователь взаимодействует с системой через **Telegram Bot**.\
Система принимает задачу, помещает её в очередь и выполняет через
AI‑агентов.

Основная цель архитектуры --- создать **platform of specialized agents
and agent teams**, которая сможет выполнять реальные рабочие задачи и
масштабироваться на новые бизнес-сценарии.

Текущий `Document Analysis Agent` --- это первый production-tested
агент, а не конечная форма системы.

------------------------------------------------------------------------

# High Level Architecture

User\
↓\
Telegram Bot\
↓\
Backend API\
↓\
PostgreSQL + Redis\
↓\
Orchestration + Worker Runtime\
↓\
Specialized Agents / Agent Teams\
↓\
Result

------------------------------------------------------------------------

# System Components

## Telegram Bot

Расположение:

    bot/

Функции:

-   интерфейс взаимодействия с пользователем
-   приём команд
-   отправка задач в backend
-   отображение результатов выполнения

Поддерживаемые команды:

    /start
    /health
    /task

Пример:

    /task Проанализируй материалы клиента

------------------------------------------------------------------------

## Backend (FastAPI)

Расположение:

    backend/

Функции:

-   API системы
-   создание задач
-   управление статусами
-   взаимодействие с Redis и PostgreSQL

Endpoints:

    GET /health
    POST /tasks

Пример запроса:

``` json
{
  "input_text": "Проанализируй материалы клиента"
}
```

Пример ответа:

``` json
{
  "id": "uuid",
  "text": "test",
  "status": "created"
}
```

------------------------------------------------------------------------

## PostgreSQL

Используется для хранения:

-   задач
-   статусов
-   результатов выполнения
-   истории обработки

Основная таблица:

    tasks

  field        description
  ------------ --------------------------
  id           уникальный идентификатор
  text         текст задачи
  status       статус задачи
  created_at   дата создания
  updated_at   дата обновления
  result       результат выполнения

------------------------------------------------------------------------

## Redis

Redis используется как **очередь задач**.

Backend кладёт задачу в очередь:

    tasks_queue

Worker забирает задачи из этой очереди.

------------------------------------------------------------------------

## Worker

Worker --- это сервис, который выполняет задачи.

Функции:

-   слушает Redis очередь
-   получает task_id
-   загружает задачу из базы
-   вызывает AI
-   сохраняет результат

Расположение:

    worker/

Штатный режим:

    ai_worker (compose service)

Ручной запуск внутри `ai_backend` используется только как
debug/fallback для диагностики.

------------------------------------------------------------------------

# Task Lifecycle

created\
↓\
queued\
↓\
running\
↓\
done / failed

------------------------------------------------------------------------

# Task Execution Pipeline

Telegram\
↓\
Bot\
↓\
Backend\
↓\
PostgreSQL\
↓\
Redis Queue\
↓\
Worker\
↓\
AI Processing\
↓\
Result

------------------------------------------------------------------------

# Platform Model

Платформа должна поддерживать:

- specialized agents
- agent teams
- orchestration layer
- approval-oriented workflows

Базовая схема:

Orchestration Layer\
↓\
├── Document Analysis Agent\
├── Analyst Agent\
├── Research Agent\
├── Writer Agent\
├── Tool Agent\
└── Approval Step

------------------------------------------------------------------------

# Core Platform Entities

## Agent

Специализированная единица исполнения с понятной ролью и контрактом
результата.

## Agent Capability

Конкретная способность агента: анализ документа, маршрутизация,
подготовка ответа, поиск фактов, интеграция с инструментами.

## Agent Team

Набор агентов, работающих вместе над одним бизнес-сценарием.

## Task

Единица работы, которая может быть передана одному агенту или целой
команде агентов.

## Task Routing

Логика выбора нужного агента или агентной команды под конкретную
задачу.

## Agent Result Contract

Нормализованный формат результата для безопасного handoff между
агентами и слоями системы.

## Approval Step

Шаг подтверждения, где результат может быть проверен человеком или
policy-логикой до следующего этапа.

------------------------------------------------------------------------

## Orchestration Layer

Функции:

-   анализ задачи
-   разбиение задачи на подзадачи
-   распределение задач между агентами
-   контроль выполнения
-   маршрутизация задач в agent teams
-   управление approval-oriented workflow шагами

------------------------------------------------------------------------

## Analyst Agent

Функции:

-   анализ входных данных
-   выделение проблем
-   структурирование информации

------------------------------------------------------------------------

## Research Agent

Функции:

-   поиск информации
-   проверка фактов
-   сбор контекста

------------------------------------------------------------------------

## Writer Agent

Функции:

-   генерация текстов
-   подготовка отчётов
-   формирование итоговых результатов

------------------------------------------------------------------------

## Tool Agent

Функции:

-   вызов внешних инструментов
-   работа с API
-   интеграции

------------------------------------------------------------------------

# Docker Architecture

Текущие контейнеры:

    bot
    backend
    worker
    redis
    postgres

`worker` уже является штатным compose service и представляет текущий
runtime для первого production-tested агента.

Orchestration:

    docker-compose

------------------------------------------------------------------------

# Project Structure

    ai-assistant
    │
    ├── bot
    ├── backend
    ├── worker
    ├── infra
    │
    └── docs
        ├── ai_assistant_memory.md
        ├── 00_overview/
        ├── 01_mvp/
        ├── 02_execution_pipeline/
        ├── 03_operations/
        └── 04_future_architecture/

------------------------------------------------------------------------

# Development Workflow

    VS Code
    Remote SSH
    Git
    Docker
    Codex

Планируется добавить:

    OpenClaw

------------------------------------------------------------------------

# Development Roadmap

## Stage 1 --- MVP Infrastructure

✔ Telegram Bot\
✔ FastAPI Backend\
✔ Task creation\
✔ Docker stack

------------------------------------------------------------------------

## Stage 2 --- Task Execution

-   PostgreSQL task storage
-   Redis queue
-   Worker service
-   Telegram delivery
-   attachment extraction

------------------------------------------------------------------------

## Stage 3 --- AI Execution

-   LLM integration
-   task processing
-   results storage

Текущий validated agent:

-   Document Analysis Agent

------------------------------------------------------------------------

## Stage 4 --- Multi-Agent System

-   orchestration layer
-   specialized agents
-   agent teams
-   approval-oriented workflows
-   tool ecosystem

Likely next business scenario:

-   email-driven multi-agent workflow

------------------------------------------------------------------------

# Key Design Principles

1.  Event‑driven architecture\
2.  Queue‑based execution\
3.  Scalable workers\
4.  Modular AI agents\
5.  Separation of concerns
