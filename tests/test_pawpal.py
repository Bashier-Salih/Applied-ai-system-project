from pawpal_system import Task, Pet


def test_mark_complete_changes_status():
    task = Task(name="Morning walk", type="walk", duration=30, priority="high")
    assert task.completed is False
    task.mark_complete()
    assert task.completed is True


def test_add_task_increases_pet_task_count():
    pet = Pet(name="Biscuit", species="Dog", breed="Golden Retriever", age=4)
    assert len(pet.get_tasks()) == 0
    pet.add_task(Task(name="Breakfast", type="feeding", duration=10, priority="high"))
    assert len(pet.get_tasks()) == 1
