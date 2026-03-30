# Contributing to Alita

Thank you for considering contributing to Alita! This document provides guidelines for contributing to the project.

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone https://github.com/yourusername/alita.git`
3. Create a virtual environment: `python -m venv venv`
4. Activate the virtual environment:
   - Windows: `venv\Scripts\activate`
   - Linux/Mac: `source venv/bin/activate`
5. Install dependencies: `pip install -r requirements.txt`
6. If you add a new Python dependency, make sure to add it to `requirements.txt` and notify other contributors to run `pip install -r requirements.txt`.
   - For example, if you add `qdrant-client`, add it to `requirements.txt` and inform the team.

## Development Workflow

1. Create a new branch: `git checkout -b feature/your-feature-name`
2. Make your changes
3. Run tests: `pytest`
4. Run linting: `flake8 .`
5. Commit your changes: `git commit -m "Add your message"`
6. Push to your fork: `git push origin feature/your-feature-name`
7. Create a Pull Request

## Code Standards

- Follow PEP 8 style guidelines
- Write type hints for all functions
- Add docstrings to all classes and functions
- Keep functions small and focused
- Write tests for new features

## Commit Message Guidelines

- Use present tense ("Add feature" not "Added feature")
- Use imperative mood ("Move cursor to..." not "Moves cursor to...")
- Limit the first line to 72 characters
- Reference issues and pull requests when relevant

## Testing

- Write unit tests for all new code
- Ensure all tests pass before submitting PR
- Aim for high test coverage
- Test both success and error cases

## Questions?

Feel free to open an issue for any questions or concerns.
